from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    """销售工具中默认不同商品之间的统一商品模型"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    price: float = Field(ge=0)
    #介绍
    summary: str = ""
    specifications: dict[str, str] = Field(default_factory=dict)
    stock: int = Field(default=0, ge=0)
    promotions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    def to_search_dict(self) -> dict:
        return self.model_dump(
            include={"product_id", "name", "category", "price", "summary"}
        )

    def to_detail_dict(self) -> dict:
        return self.model_dump(
            include={
                "product_id",
                "name",
                "category",
                "price",
                "summary",
                "specifications",
            }
        )
