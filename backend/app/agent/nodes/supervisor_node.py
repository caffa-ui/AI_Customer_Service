from app.agent.agent_config.llm_config import llm
from app.agent.memory import (
    get_memory_summary,
    get_recent_messages,
    messages_to_context,
)
from app.agent.State.state import SCRMState
from app.utils.prompt_handler import load_supervisor_prompt
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
        #将列表转换成字符串，以"，"相隔
        "tags": ", ".join(user_tags) if user_tags else "None",
        "gender": gender_info,
        "memory_summary": memory_summary,
        "recent_context": recent_context,
        "input": latest_user_input
    })

    intent=response.content.strip().lower()

    if intent not in ["sale","support","chat"]:
        #如果大模型输出了别的，默认导向销售节点
        intent="sale"

    print(f"[Supervisor] 决策完毕 -> 当前分发路由: {intent}")

    #这是LangGraph的State更新机制节点函数返回一个字典，LangGraph会自动把返回的字典合并到State里
    return {"current_intent": intent}


#闲聊节点
def chat_node(state: SCRMState):
    """
    SCRM 闲聊/安抚智能体：
    负责处理用户的日常问候、无意义输入或纯闲聊。
    核心商业目的：提供情绪价值，并高情商地将话题引导回商品转化或服务上。
    """
    user_tags = state.get("user_tags", [])

    user_gender = state.get("user_gender") or "未提供"
    user_name = state.get("user_name") or "未提供"
    tag_str = ", ".join(user_tags) if user_tags else "无特别偏好"
    memory_summary = get_memory_summary(state)

    system_prompt = """
         你是一名 SCRM 系统的专属客服管家。当前用户正在和你进行日常闲聊、打招呼或输入了简短的词语。

    【长期会话记忆（重要背景）】
    {memory_summary}

    如果长期记忆与用户最新输入冲突，以最新输入为准。

    【当前客户画像】
    - 称呼：{name}
    - 性别：{gender_info}
    - 历史标签：{tags_str}

    【高情商沟通策略 - 企业红线】
    1. 热情回应：结合客户的称呼，以朋友的口吻自然、亲切地回应用户的闲聊或问候。
    2. 情绪共鸣：展现出极高的情商，不机械、不敷衍。如果用户发表情或语气词，你要能接得住梗。
    3. 【核心任务】商业引流：在闲聊回应的最后，必须极其自然地用一句话将话题引导回业务上。
       - 例如引导导购：“对了，最近店里上了几款符合您喜好的新品，需要我给您介绍下吗？”
       - 例如引导售后：“最近有遇到什么需要我帮忙解决的售后问题吗？”
    4. 长度控制：回复务必简短精炼，营造轻松的聊天氛围，绝对不要像写小作文一样长篇大论。
         """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        # MessagesPlaceholder 专门用来安全地插入历史消息列表
        MessagesPlaceholder(variable_name="chat_history")
    ])

    chain = prompt | llm

    recent_messages = get_recent_messages(state)

    print(f"[系统提示] 正在结合画像 (性别:{user_gender}, 标签:{tag_str}) 思考...")

    # 触发调用
    response = chain.invoke({
        "name": user_name,
        "gender_info": user_gender,
        "tags_str": tag_str,
        "memory_summary": memory_summary,
        "chat_history": recent_messages
    })

    print(f"[AI 导购]: {response.content}")

    return {"messages": [response]}
