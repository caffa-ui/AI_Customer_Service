from typing import TypedDict, Annotated, Optional, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document

#标签去重
def add_tags(left:list[str], right:list[str])->list[str]:
    return list(set(left+right))

class InputState(TypedDict):
    pass

class OutputState(TypedDict):
    pass

class PrivateState(TypedDict):
    pass

class SCRMState(TypedDict):
    #核心状态，承载聊天记录
    messages: Annotated[list[BaseMessage], add_messages]

    current_intent: Optional[Literal["sale","support","chat"]]

    support_intent: Optional[Literal["general", "refund"]]
    refund_status: Optional[Literal["pending", "approved", "rejected"]]
    refund_ticket_id: str | None
    refund_thread_id: str | None
    conversation_id: str | None

    user_id: str
    user_name: Optional[str]
    user_gender: Optional[Literal["male", "female"]]
    user_tags: Annotated[list[str], add_tags]
    summary: str

    rag_support_state: Optional[Literal["yes","no"]]
    rag_retrieve_docs: list[dict]
    rag_query: str | None
    rag_grade: Optional[Literal["yes","no"]]
    rag_retrieve_error: str | None
    rewrite_test: int
