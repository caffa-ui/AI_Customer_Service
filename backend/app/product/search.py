from collections.abc import Iterable

from app.product.models import Product


def rank_products(
    products: Iterable[Product],
    *,
    query: str = "",
    category: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 5,
) -> list[Product]:
    """静态与MySQL Repository共用同一套商品筛选和排序规则。"""
    normalized_query = query.strip().casefold()
    normalized_category = category.strip().casefold()
    scored_matches: list[tuple[int, Product]] = []

    for product in products:
        searchable_text = " ".join(
            [
                product.product_id,
                product.name,
                product.category,
                product.summary,
                *product.keywords,
                *product.specifications.values(),
            ]
        ).casefold()
        score = 0
        if normalized_query:
            if normalized_query in searchable_text:
                score += 3
            query_terms = normalized_query.replace("，", " ").split()
            score += sum(1 for term in query_terms if term in searchable_text)
            score += sum(
                2
                for keyword in product.keywords
                if keyword.casefold() in normalized_query
            )
            if score == 0:
                continue
        if normalized_category and normalized_category not in product.category.casefold():
            continue
        if min_price is not None and product.price < min_price:
            continue
        if max_price is not None and product.price > max_price:
            continue
        scored_matches.append((score, product))

    if normalized_query:
        scored_matches.sort(key=lambda item: item[0], reverse=True)
    return [product for _, product in scored_matches[:limit]]
