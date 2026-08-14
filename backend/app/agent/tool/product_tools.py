from langchain_core.tools import BaseTool
from langchain.tools import tool

from app.product.service import ProductService


def create_product_tools(service: ProductService) -> list[BaseTool]:
    """销售智能体商品查询工具"""

    @tool
    async def search_products(
        query: str = "",
        category: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 5,
    ) -> dict:
        """
        根据需求关键词、商品分类和可选价格区间搜索商品。
        用户尚未提供明确商品编号，或要求推荐、筛选、比较候选商品时调用。
        query 可填写用途或偏好；category 不明确时留空；limit 通常不超过 5。
        """
        return await service.search_products(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
        )

    @tool
    async def get_product_details(product_id: str) -> dict:
        """
        根据明确商品编号查询名称、价格、规格和产品说明。
        用户询问某个具体商品参数时调用；没有商品编号时先调用 search_products。
        """
        return await service.get_product_details(product_id)

    @tool
    async def check_inventory(product_id: str) -> dict:
        """
        根据明确商品编号查询当前库存数量和是否有货。
        库存信息必须以本工具本轮返回结果为准，不要依据历史对话推测。
        """
        return await service.check_inventory(product_id)

    @tool
    async def get_current_promotions(product_id: str) -> dict:
        """
        根据明确商品编号查询当前价格和有效促销说明。
        价格与优惠必须以本工具本轮返回结果为准，不要自行计算或承诺额外优惠。
        """
        return await service.get_current_promotions(product_id)

    #如果返回有警告不用管，属于是PyCharm静态类型误报
    return [
        search_products,
        get_product_details,
        check_inventory,
        get_current_promotions,
    ]
