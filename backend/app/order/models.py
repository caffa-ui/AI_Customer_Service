from pydantic import BaseModel, ConfigDict, Field


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)


class Order(BaseModel):
    """售后工具与不同订单数据源之间的统一订单模型"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    order_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    total_amount: float = Field(ge=0)
    items: list[OrderItem] = Field(default_factory=list)
    carrier: str = ""
    tracking_number: str = ""
    logistics_status: str = ""
    latest_logistics: str = ""
    estimated_delivery: str = ""

    def to_public_dict(self) -> dict:
        return self.model_dump(
            exclude={
                "user_id",
                "carrier",
                "tracking_number",
                "logistics_status",
                "latest_logistics",
                "estimated_delivery",
            }
        )

    def to_logistics_dict(self) -> dict:
        return self.model_dump(
            include={
                "order_id",
                "carrier",
                "tracking_number",
                "logistics_status",
                "latest_logistics",
                "estimated_delivery",
            }
        )
