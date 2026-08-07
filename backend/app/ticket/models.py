from pydantic import BaseModel, ConfigDict, Field


class Ticket(BaseModel):
    """智能体与不同工单数据源之间的统一工单模型。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    ticket_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    ticket_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    latest_note: str = ""
    subject: str = ""
    description: str = ""

    def to_public_dict(self) -> dict:
        """移除内部用户标识，只向智能体暴露必要工单字段。"""
        return self.model_dump(exclude={"user_id"})
