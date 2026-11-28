from collections.abc import Callable

from spider.application.ports import SiteClient
from spider.domain.order import Order

SITE = "https://www.dollyteria.com"
SALES_HISTORY_URL = f"{SITE}/sales-history"


class ProductNotFound(Exception):
    """一覧ページに商品名が見つからない。"""


async def get_latest_product_name(
    client: SiteClient, url: str, extract: Callable[[str], str]
) -> str:
    return extract(await client.get(url))


async def get_purchase_history(
    client: SiteClient,
    email: str,
    password: str,
    extract: Callable[[str], list[Order]],
) -> list[Order]:
    await client.login(email, password)
    return extract(await client.get(SALES_HISTORY_URL))
