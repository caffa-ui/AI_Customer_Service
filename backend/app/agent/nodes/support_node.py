from collections.abc import Sequence

from app.agent.agent_config.llm_config import llm
from app.agent.memory import get_memory_summary, get_recent_messages
from app.agent.State.state import SCRMState
from app.utils.prompt_handler import load_support_prompt
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def create_support_node(tools: Sequence[BaseTool] = ()):
    """创建可按需绑定业务工具的售后节点。"""

    async def support_node_with_tools(state: SCRMState):
        user_name=state.get("user_name") or "未提供"
        user_gender=state.get("user_gender") or "未提供"
        user_tag=state.get("user_tags",[])
        tags_str=",".join(user_tag) if user_tag else "无特别偏好"
        memory_summary = get_memory_summary(state)

        system_prompts = load_support_prompt()

        prompt=ChatPromptTemplate.from_messages(
            [
                ("system", system_prompts),
                MessagesPlaceholder(variable_name="chat_history"),
            ]
        )

        active_model = llm.bind_tools(list(tools)) if tools else llm
        chain = prompt | active_model

        recent_message = get_recent_messages(state)

        response=await chain.ainvoke(
            {
                "name":user_name,
                "gender_info":user_gender,
                "tags_str": tags_str,
                "memory_summary": memory_summary,
                "chat_history":recent_message,
            }
        )

        if response.content:
            print(f"[售后专家]: {response.content}")
        elif getattr(response, "tool_calls", None):
            tool_names = ", ".join(call["name"] for call in response.tool_calls)
            print(f"[售后专家] 请求调用工具: {tool_names}")

        return {"messages": [response]}

    return support_node_with_tools


# 保留原有导入入口；正式图会通过 create_support_node 绑定工具。
support_node = create_support_node()
