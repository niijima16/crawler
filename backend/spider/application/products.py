import asyncio
from collections.abc import Callable
from urllib.parse import urlencode

from spider.application.ports import SiteClient
from spider.application.use_cases import SITE
from spider.domain.product import ProductSummary


async def get_product(
    client: SiteClient,
    product_id: int,
    extract: Callable[[str, int], ProductSummary],
) -> ProductSummary:
    return extract(await client.get(f"{SITE}/product/{product_id}"), product_id)


async def search_products(
    client: SiteClient,
    keyword: str,
    extract_results: Callable[[str, set[int]], list[ProductSummary]],
    extract_ids: Callable[[str], set[int]],
) -> list[ProductSummary]:
    """部分一致検索。一覧では在庫の有無が分からないため、在庫ありのみの検索との差で判定する。"""
    query = urlencode({"keyword": keyword})
    everything, in_stock = await asyncio.gather(
        client.get(f"{SITE}/product-list?{query}"),
        client.get(f"{SITE}/product-list?{query}&available=1"),
    )
    return extract_results(everything, extract_ids(in_stock))
