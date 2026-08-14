from app.agent.agent_config.llm_config import llm
from app.agent.memory import (
    get_memory_summary,
    get_recent_messages,
    messages_to_context,
)
from app.agent.State.state import SCRMState
from app.utils.prompt_handler import load_supervisor_prompt,load_chat_prompt
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage


#主管节点
def supervisor_node(state:SCRMState):
    chat_history=state.get("messages",[])

    #获取用户最新输入,且确保是用户发出的最新消息
    latest_user_input = next(
    (m.content for m in reversed(chat_history) if isinstance(m, HumanMessage)
     ),"")

    user_tags=state.get("user_tags",[])
    gender_info=state.get("user_gender","未知")
    memory_summary = get_memory_summary(state)
    previous_messages = (
        chat_history[:-1]
        if chat_history and isinstance(chat_history[-1], HumanMessage)
        else chat_history
    )
    recent_context = messages_to_context(previous_messages)

    system_prompt = load_supervisor_prompt()

    prompt=ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "用户最新输入的消息是:{input}")
    ])

    chain= prompt | llm

    response = chain.invoke({
        #将列表转换成字符串
        "tags": ", ".join(user_tags) if user_tags else "None",
        "gender": gender_info,
        "memory_summary": memory_summary,
        "recent_context": recent_context,
        "input": latest_user_input
    })

    #出错点，要全转小写
    intent=response.content.strip().lower()

    if intent not in ["sale","support","chat"]:
        #防止大模型输出了别的，强制导向销售节点
        intent="sale"

    print(f"[Supervisor] 决策完毕 -> 当前分发路由: {intent}")

    return {"current_intent": intent}


#闲聊节点
def chat_node(state: SCRMState):
    """
    闲聊智能体:主要提供情绪价值，并高情商地将话题引导回商品转化或服务上。
    """
    user_tags = state.get("user_tags", [])

    user_gender = state.get("user_gender") or "未提供"
    user_name = state.get("user_name") or "未提供"
    tag_str = ", ".join(user_tags) if user_tags else "无特别偏好"
    memory_summary = get_memory_summary(state)

    system_prompt = load_chat_prompt()

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        #用于结构化插入近期聊天消息
        MessagesPlaceholder(variable_name="chat_history")
    ])

    chain = prompt | llm

    recent_messages = get_recent_messages(state)

    print(f"[系统提示] 正在结合画像 (性别:{user_gender}, 标签:{tag_str}) 思考...")

    response = chain.invoke({
        "name": user_name,
        "gender_info": user_gender,
        "tags_str": tag_str,
        "memory_summary": memory_summary,
        "chat_history": recent_messages
    })

    print(f"[AI 导购]: {response.content}")

    return {"messages": [response]}
