from collections.abc import Callable

from spider.application.ports import SiteClient, UpstreamError
from spider.application.use_cases import SITE
from spider.domain.keyword_favorite import GENRES, Genre

# カテゴリのドロップダウンは、ログイン不要のこのページに全件出ている。
_CATEGORY_PAGE = f"{SITE}/product-list/22"


class SiteCategoryProvider:
    """サイトからカテゴリ一覧を取得し TTL の間キャッシュする。

    取り直しに失敗したら前回の一覧を返す（21時の混雑の 503 など）。一度も取れていなければ GENRES。
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[], SiteClient],
        parse: Callable[[str], list[Genre]],
        now: Callable[[], float],
        ttl_seconds: float,
    ) -> None:
        self._client_factory = client_factory
        self._parse = parse
        self._now = now
        self._ttl = ttl_seconds
        self._cached: list[Genre] | None = None
        self._fetched_at = 0.0

    async def list_categories(self) -> list[Genre]:
        if self._cached is not None and self._now() - self._fetched_at < self._ttl:
            return self._cached
        categories = await self._fetch()
        if categories:
            self._cached = categories
            self._fetched_at = self._now()
            return categories
        return self._cached or list(GENRES)

    async def _fetch(self) -> list[Genre]:
        client = self._client_factory()
        try:
            html = await client.get(_CATEGORY_PAGE)
        except UpstreamError:
            return []
        finally:
            await client.aclose()
        return self._parse(html)
