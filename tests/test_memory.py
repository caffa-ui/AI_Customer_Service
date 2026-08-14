from pathlib import Path
import sys
import unittest

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.memory import MAX_SUMMARY_CHARS, get_memory_summary
import app.agent.nodes.sale_node as sale_module
import app.agent.nodes.summarize_node as summarize_module
import app.agent.nodes.supervisor_and_chat_node as supervisor_module
import app.agent.nodes.support_classifier_node as classifier_module
import app.agent.nodes.support_node as support_module


class RecordingChatModel(BaseChatModel):
    responses: list[str]
    captured_batches: list[list[BaseMessage]] = Field(default_factory=list)
    response_index: int = 0

    @property
    def _llm_type(self) -> str:
        return "recording-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured_batches.append(list(messages))
        response = self.responses[self.response_index]
        self.response_index += 1
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=response))]
        )

    def bind_tools(self, tools, **kwargs):
        return self


def prompt_text(model: RecordingChatModel) -> str:
    return "\n".join(
        str(message.content)
        for batch in model.captured_batches
        for message in batch
    )


def state_with_memory() -> dict:
    return {
        "messages": [
            HumanMessage(content="请先推荐 A 和 B"),
            AIMessage(content="A 更注重性能，B 更注重性价比"),
            HumanMessage(content="那第二个呢？"),
        ],
        "user_id": "cli-user",
        "user_name": None,
        "user_gender": None,
        "user_tags": [],
        "summary": "用户预算 5000 元，偏好性价比，不接受超出预算的方案。",
    }


class MemoryInjectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_sale_llm = sale_module.llm
        self.original_supervisor_llm = supervisor_module.llm
        self.original_classifier_llm = classifier_module.llm
        self.original_support_llm = support_module.llm

    def tearDown(self):
        sale_module.llm = self.original_sale_llm
        supervisor_module.llm = self.original_supervisor_llm
        classifier_module.llm = self.original_classifier_llm
        support_module.llm = self.original_support_llm

    async def test_sale_chat_and_support_receive_long_term_summary(self):
        state = state_with_memory()

        sale_model = RecordingChatModel(responses=["sale-ok"])
        sale_module.llm = sale_model
        await sale_module.sale_node(state)
        self.assertIn("用户预算 5000 元", prompt_text(sale_model))

        chat_model = RecordingChatModel(responses=["chat-ok"])
        supervisor_module.llm = chat_model
        supervisor_module.chat_node(state)
        self.assertIn("用户预算 5000 元", prompt_text(chat_model))

        support_model = RecordingChatModel(responses=["support-ok"])
        support_module.llm = support_model
        support_node = support_module.create_support_node()
        await support_node(state)
        self.assertIn("用户预算 5000 元", prompt_text(support_model))

    async def test_classifiers_receive_summary_and_recent_context(self):
        state = state_with_memory()

        supervisor_model = RecordingChatModel(responses=["sale"])
        supervisor_module.llm = supervisor_model
        result = supervisor_module.supervisor_node(state)
        text = prompt_text(supervisor_model)
        self.assertEqual(result["current_intent"], "sale")
        self.assertIn("用户预算 5000 元", text)
        self.assertIn("A 更注重性能，B 更注重性价比", text)

        classifier_model = RecordingChatModel(responses=["general"])
        classifier_module.llm = classifier_model
        result = classifier_module.support_classifier_node(state)
        text = prompt_text(classifier_model)
        self.assertEqual(result["support_intent"], "general")
        self.assertIn("用户预算 5000 元", text)
        self.assertIn("A 更注重性能，B 更注重性价比", text)

    async def test_memory_is_read_from_each_state_without_cross_user_leakage(self):
        first = state_with_memory()
        second = state_with_memory()
        second["summary"] = "另一位用户只关心售后维修。"

        self.assertIn("5000", get_memory_summary(first))
        self.assertNotIn("5000", get_memory_summary(second))


class SummarizeMemoryTests(unittest.TestCase):
    def setUp(self):
        self.original_llm = summarize_module.llm

    def tearDown(self):
        summarize_module.llm = self.original_llm

    @staticmethod
    def long_history() -> list[BaseMessage]:
        messages: list[BaseMessage] = [
            HumanMessage(content="请查询工单", id="human-tool"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_ticket",
                        "args": {"ticket_id": "TK-10001"},
                        "id": "call-ticket",
                    }
                ],
                id="ai-tool-call",
            ),
            ToolMessage(
                content='{"ok": true, "ticket": {"ticket_id": "TK-10001", "status": "pending"}}',
                tool_call_id="call-ticket",
                id="tool-result",
            ),
            AIMessage(content="工单正在等待审核", id="ai-tool-final"),
        ]
        for index in range(1, 12):
            long_text = f"第 {index} 轮历史内容 " + ("用户偏好性价比。" * 180)
            messages.extend(
                [
                    HumanMessage(content=long_text, id=f"human-{index}"),
                    AIMessage(content=long_text, id=f"ai-{index}"),
                ]
            )
        return messages

    def test_summary_preserves_tool_result_rules_and_enforces_length(self):
        model = RecordingChatModel(responses=["摘要" * (MAX_SUMMARY_CHARS + 20)])
        summarize_module.llm = model
        state = {
            "messages": self.long_history(),
            "summary": "之前已知用户预算 5000 元。",
        }

        result = summarize_module.summarize_node(state)
        text = prompt_text(model)

        self.assertIn("tool_result(工具已确认)", text)
        self.assertIn("TK-10001", text)
        self.assertIn("之前已知用户预算 5000 元", text)
        self.assertLessEqual(len(result["summary"]), MAX_SUMMARY_CHARS)
        self.assertGreater(len(result["messages"]), 0)


if __name__ == "__main__":
    unittest.main()
