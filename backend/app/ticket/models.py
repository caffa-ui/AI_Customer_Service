from pydantic import BaseModel, ConfigDict, Field


class Ticket(BaseModel):
    """智能体与不同工单数据库之间的统一工单模型"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    ticket_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    ticket_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    latest_note: str = ""
    subject: str = ""
    description: str = ""
    order_id: str | None = None
    conversation_id: str | None = None
    refund_thread_id: str | None = None
    reviewer_id: str | None = None
    review_note: str | None = None
    reviewed_at: str | None = None

    def to_public_dict(self) -> dict:
        """移除内部用户标识，只向智能体暴露必要工单字段"""
        return self.model_dump(
            exclude={
                "user_id",
                "conversation_id",
                "refund_thread_id",
                "reviewer_id",
            }
        )

    def to_admin_dict(self) -> dict:
        """管理员审核接口使用的完整工单信息"""
        return self.model_dump(exclude={"user_id"})
