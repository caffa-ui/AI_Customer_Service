from collections.abc import Sequence

from claude_agent_sdk import rename_session_via_store
from langchain_core import chat_history
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool

from app.agent.agent_config.llm_config import llm
from app.agent.State.state import SCRMState
from app.agent.memory import exclude_tools_content
from app.utils.prompt_handler import load_rag_prompt
from app.knowledge.service import  KnowledgeService


async def rag_determine_agent_node(state: SCRMState):
    """判断是否需要使用检索"""

    chat_history = state.get("messages", [])

    latest_user_input = ""
    for m in reversed(chat_history):
        if isinstance(m, HumanMessage):
            latest_user_input = m.content.strip()
            break

    previous_messages = (
        chat_history[:-1]
        if chat_history and isinstance(chat_history[-1], HumanMessage)
        else chat_history
    )

    recent_content = exclude_tools_content(previous_messages)

    system_prompt = """
    你是一名售后知识检索判断器。

    请以近期对话为背景，重点判断用户最新输入是否在询问：
    - 故障排查；
    - 退换货规则；
    - 物流处理办法。

    【近期对话】
    {recent_content}

    【强制输出】
    如果需要查询售后知识库，只输出 "yes"。
    如果不需要查询售后知识库，只输出 "no"。
    绝不输出其他字符。
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "用户最新输入: {input}")
    ])

    chain = prompt | llm

    response = await chain.ainvoke({
        "recent_content": recent_content,
        "input": latest_user_input
    })

    rag_support_state = response.content.strip().lower()

    if rag_support_state not in ["yes","no"]:
        rag_support_state = "yes"

    return {"rag_support_state": rag_support_state }

async def rewrite_query_node(state: SCRMState):
    """优化query，实现更加精准的检索查询"""

    query = state.get("rag_query") or ""

    if not query:
        chat_history = state.get("messages", [])

        for m in reversed(chat_history):
            if isinstance(m, HumanMessage):
                query = m.content.strip()
                break

    system_prompt = """
        请优化下面这个问题，使其更适合用于售后知识库检索。

        要求：
        1. 保留故障对象、业务规则或处理目标。
        2. 不得添加原问题中不存在的事实。
        3. 只返回一条优化后的检索语句，不要解释。

        原始问题：
        {question}
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system",system_prompt)
        ])

    chain = prompt | llm

    response = await chain.ainvoke({
        "question": query
    })

    new_query = response.content.strip()

    return {
        "rag_query": new_query,
        "rewrite_test": (state.get("rewrite_test", 0) or 0) + 1
        }


async def grade_doucments_node(state: SCRMState):
    """判断检索资料是否足够"""

    docs = state.get("rag_retrieve_docs")
    chat_history = state.get("messages")

    last_user_input = ""
    for m in reversed(chat_history):
        if isinstance(m,HumanMessage):
            last_user_input = m.content.strip()
            break

    system_prompt = """ 
    你是一个检索结果评估器。
    
    用户问题:
    {qusetion}
    
    检索结果:
    {documents}
    
    【强制要求】
    当判断这些检索能够回答用户问题是输出"yes"
    不能时输出"no"
    绝不输出其他字符。
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt)
    ])

    chain = prompt | llm

    response = await chain.ainvoke({
        "qusetion": last_user_input,
        "documents": docs
    })

    grade = response.content.strip().lower()

    return {"rag_grade": grade}

def create_retrieve_documents_node(servise: KnowledgeService):
    async def get_retrieve_documents(state: SCRMState):
        """通过原先的tool改写出来的售后知识文档检索获取"""

        query = state.get("rag_query")

        result = await servise.search_support_knowledge(
            query = query
        )

        if not result.get("ok"):
            return {
                "rag_retrieve_docs": [],
                "rag_retrieve_error": result.get(
                    "error_code"
                )
            }

        return {
            "rag_retrieve_docs": result.get("articles",[]),
            "rag_retrieve_error": None
        }

    return get_retrieve_documents


