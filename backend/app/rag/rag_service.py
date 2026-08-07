from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from app.rag.vector_store import VectorStoreService
from app.utils.prompt_handler import load_rag_prompt
from app.model.factory import get_chat_model

class RagSummarizeService:
    def __init__(self):
        self.vector_store=VectorStoreService()
        self.retriever=self.vector_store.get_retriever()
        self.prompt_txt=load_rag_prompt()
        self.prompt_template=PromptTemplate.from_template(self.prompt_txt)
        self.model=get_chat_model()
        self.chain=self.__init__chain()

    def __init__chain(self):
        chain=self.prompt_template | self.model | StrOutputParser()
        return chain

    def retriever_docs(self,query: str)->list[Document]:
        return self.retriever.invoke(query)

    def rag_summarize(self,query:str) -> str:
        context_docs=self.retriever_docs(query)

        context=""
        counter=0
        for doc in context_docs:
            counter+=1
            context+=f"【参考资料{counter}】:参考资料: {doc.page_content} | 参考元数据: {doc.metadata}\n"

        return self.chain.invoke(
            {
                "input":query,
                "context": context
            }
        )

    # 保留原有拼写，避免已有调用方立即失效。
    def rag_summerize(self, query: str) -> str:
        return self.rag_summarize(query)
