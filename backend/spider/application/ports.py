from datetime import datetime
from typing import Literal, Protocol

from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite, FavoriteState
from spider.domain.keyword_favorite import Genre, KeywordFavorite


class LoginFailed(Exception):
    """ログインに失敗した。"""


class UpstreamError(Exception):
    """上流サイトへのリクエストが失敗した（接続エラー・5xx など）。"""


class PreviewTimeout(Exception):
    """制限時間内に処理を完了できなかった。"""


class NotPurchasable(Exception):
    """商品を購入できない（売り切れなど。カートに入らない）。"""


class PaymentMethodUnavailable(Exception):
    """選んだ支払方法が、この商品・アカウントでは選べない。"""


class HandoffAndSubmit(Exception):
    """handoff と submit_order は同時に指定できない。"""


class OrderSubmitDisabled(Exception):
    """サーバー設定で注文確定が許可されていない。"""


class UnsupportedPaymentMethod(Exception):
    """この支払方法は未対応（unknown: 未知 / preview: 確認画面まで不可 / submit: 注文確定不可）。"""

    def __init__(self, reason: Literal["unknown", "preview", "submit"]) -> None:
        super().__init__(reason)
        self.reason = reason


class SiteClient(Protocol):
    async def login(self, email: str, password: str) -> None: ...

    async def get(self, url: str) -> str: ...

    async def post(self, url: str, data: dict[str, str]) -> str: ...

    def get_cookie(self, name: str) -> str | None: ...

    async def aclose(self) -> None: ...


class CategoryProvider(Protocol):
    async def list_categories(self) -> list[Genre]: ...


class EntityNotFound(Exception):
    """アカウント・お気に入りが見つからない。"""


class DuplicateAccount(Exception):
    """同じメールアドレスのアカウントがすでにある。"""


class DuplicateFavorite(Exception):
    """同じ商品がすでにお気に入りにある。"""


class FavoriteLimitReached(Exception):
    """1アカウントのお気に入りの上限に達した。"""


class InvalidTransition(Exception):
    """今の状態からは、その操作ができない。"""


class SecretBoxError(Exception):
    """暗号化された値を復号できない（鍵が違う・壊れているなど）。"""


class SecretBox(Protocol):
    def encrypt(self, plain: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AccountRepository(Protocol):
    async def add(self, account: Account, encrypted_password: str) -> None: ...

    async def list_all(self) -> list[Account]: ...

    async def get_with_secret(self, account_id: str) -> tuple[Account, str] | None: ...

    async def delete(self, account_id: str) -> None: ...


class FavoriteRepository(Protocol):
    async def add(self, favorite: Favorite) -> None: ...

    async def get(self, favorite_id: str) -> Favorite | None: ...

    async def list_all(self, account_id: str | None = None) -> list[Favorite]: ...

    async def list_active(self) -> list[Favorite]:
        """監視中（watching）と購入処理中（purchasing）。読み取りのみ。"""
        ...

    async def update_settings(
        self, favorite_id: str, payment_method: str, price_cap_yen: int | None
    ) -> bool: ...

    async def transition(
        self,
        favorite_id: str,
        current: FavoriteState,
        target: FavoriteState,
        expected_version: int,
        now: datetime,
    ) -> bool:
        """状態とバージョンが一致するときだけ遷移する（条件付き書き込み）。成功したら True。"""
        ...

    async def delete(self, favorite_id: str) -> None: ...

    async def delete_for_account(self, account_id: str) -> None: ...


class NotificationRepository(Protocol):
    async def add(self, notification: Notification) -> None: ...

    async def list_all(self, limit: int = 50) -> list[Notification]:
        """新しい順。"""
        ...

    async def unread_count(self) -> int: ...

    async def mark_all_read(self) -> None: ...


class SettingsRepository(Protocol):
    async def auto_purchase_enabled(self) -> bool: ...

    async def set_auto_purchase_enabled(self, enabled: bool) -> None: ...

    async def last_tick_at(self) -> datetime | None: ...

    async def record_tick(self, at: datetime) -> None: ...


class KeywordFavoriteRepository(Protocol):
    async def add(
        self, favorite: KeywordFavorite, seen_product_ids: set[int] | None = None
    ) -> None: ...

    async def get(self, favorite_id: str) -> KeywordFavorite | None: ...

    async def list_all(self, account_id: str | None = None) -> list[KeywordFavorite]: ...

    async def list_enabled(self) -> list[KeywordFavorite]: ...

    async def update_settings(
        self, favorite_id: str, payment_method: str, price_cap_yen: int | None
    ) -> bool: ...

    async def set_enabled(self, favorite_id: str, enabled: bool) -> bool: ...

    async def delete(self, favorite_id: str) -> None: ...

    async def delete_for_account(self, account_id: str) -> None: ...

    async def claim_product(self, favorite_id: str, product_id: int) -> bool:
        """商品IDを seen に条件付きで追加する。追加できたら True（初めて見た）。"""
        ...

    async def bump_new_arrival(self, favorite_id: str) -> None: ...
