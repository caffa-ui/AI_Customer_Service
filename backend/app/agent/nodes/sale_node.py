from collections.abc import Sequence

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from app.agent.agent_config.llm_config import llm
from app.agent.memory import get_memory_summary, get_recent_messages
from app.agent.State.state import SCRMState
from app.utils.prompt_handler import load_sale_prompt


def create_sale_node(tools: Sequence[BaseTool] = ()):
    """创建可按需绑定商品工具的销售节点。"""

    async def sale_node_with_tools(state: SCRMState):
        user_tags = state.get("user_tags", [])

        user_gender = state.get("user_gender") or "未提供"
        user_name = state.get("user_name") or "未提供"
        tag_str = ", ".join(user_tags) if user_tags else "无特别偏好"
        memory_summary = get_memory_summary(state)

        system_prompt = load_sale_prompt()

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history")
        ])

        active_model = llm.bind_tools(list(tools)) if tools else llm
        chain = prompt | active_model

        recent_messages = get_recent_messages(state)

        print(f"[系统提示] 正在结合画像 (性别:{user_gender}, 标签:{tag_str}) 思考...")

        response = await chain.ainvoke({
            "name": user_name,
            "gender_info": user_gender,
            "tags_str": tag_str,
            "memory_summary": memory_summary,
            "chat_history": recent_messages
        })

        if response.content:
            print(f"[AI 导购]: {response.content}")
        elif getattr(response, "tool_calls", None):
            tool_names = ", ".join(call["name"] for call in response.tool_calls)
            print(f"[AI 导购] 请求调用工具: {tool_names}")

        return {"messages": [response]}

    return sale_node_with_tools


# 保留原有导入入口；正式图会通过 create_sale_node 绑定工具。
sale_node = create_sale_node()
