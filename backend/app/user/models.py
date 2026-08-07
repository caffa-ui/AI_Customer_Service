from pydantic import BaseModel, ConfigDict, Field


class UserProfile(BaseModel):
    """MySQL用户主数据与智能体会话之间的稳定用户模型。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    user_name: str | None = None
    gender: str | None = None
    status: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status.casefold() == "active"
