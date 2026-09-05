from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from app.agent.agent_config.llm_config import small_llm
from app.agent.memory import get_memory_summary, messages_to_context
from app.agent.State.state import SCRMState

async def support_classifier_node(state: SCRMState):
    chat_history = state.get("messages", [])
    latest_user_input = next(
        (m.content for m in reversed(chat_history) if isinstance(m, HumanMessage)), ""
    )
    memory_summary = get_memory_summary(state)
    previous_messages = (
        chat_history[:-1]
        if chat_history and isinstance(chat_history[-1], HumanMessage)
        else chat_history
    )
    recent_context = messages_to_context(previous_messages)

    system_prompt = """
    你是一个售后意图分类器。
    请判断用户的最新输入是普通的售后咨询（如查物流、换货、故障排查），还是明确要求退款（如退钱、申请退款）。

    【长期会话记忆】
    {memory_summary}

    【最近对话上下文】
    {recent_context}

    【强制输出】
    只能输出 "refund"（要求退款）或 "general"（普通咨询），绝不包含其他字符。
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "用户最新输入: {input}")
    ])

    chain = prompt | small_llm

    response = await chain.ainvoke(
        {
            "input": latest_user_input,
            "memory_summary": memory_summary,
            "recent_context": recent_context,
        }
    )

    intent = response.content.strip().lower()

    if intent not in ["refund", "general"]:
        intent = "general"

    print(f"[Support Classifier] 售后细分意图 -> {intent}")
    return {"support_intent": intent}
