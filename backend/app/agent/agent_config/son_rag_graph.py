from typing import Literal

from langgraph.graph import START,END,StateGraph

from app.agent.State.state import SCRMState
from app.agent.nodes.Rag_agent_node import (
grade_doucments_node,
rewrite_query_node,
create_retrieve_documents_node
)
from app.knowledge.factory import create_knowledge_repository
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService

MAX_REWRITE_TEST = 3     #最大重写次数

def rag_build_graph( knowledge_repository: KnowledgeRepository | None = None):

    def router_grade_determine(state:SCRMState) -> Literal["rewrite","end"]:
        """根据评估节点的判断路由"""
        grade = state.get("rag_grade")
        retrieve_error = state.get("rag_retrieve_error")
        test = state.get("rewrite_test") or 0

        if retrieve_error or grade == "yes":
            return "end"
        elif test >= MAX_REWRITE_TEST:
            return "end"
        else:
            return "rewrite"


    knowledge_repository = knowledge_repository or create_knowledge_repository()
    knowledge_service = KnowledgeService(knowledge_repository)

    builder = StateGraph(SCRMState)

    builder.add_node("rewrite", rewrite_query_node)
    builder.add_node("get_retrieve", create_retrieve_documents_node(knowledge_service))
    builder.add_node("grade", grade_doucments_node)


    builder.add_edge(START,"rewrite")
    builder.add_edge("rewrite","get_retrieve")
    builder.add_edge("get_retrieve","grade")

    builder.add_conditional_edges(
        "grade",
        router_grade_determine,
        {
            "end": END,
            "rewrite": "rewrite"
        },
    )

    rag_graph = builder.compile()

    return rag_graph




















