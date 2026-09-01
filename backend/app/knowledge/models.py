from pydantic import BaseModel, ConfigDict, Field


class KnowledgeArticle(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    article_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(max_length=10)
    content: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    source_type: str = "rag"
    source_path: str = ""
    page: int | None = None
    score: float | None = None

    def to_public_dict(self) -> dict:
        return self.model_dump(exclude={"keywords"})
