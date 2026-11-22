"""メモリ上のリポジトリ（テスト用）。

書き込み回数を数え、条件付き遷移を DynamoDB と同じ意味で再現する。
"""

from dataclasses import dataclass, field
from datetime import datetime

from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite, FavoriteState


class MemoryAccounts:
    def __init__(self, writes: "WriteCounter") -> None:
        self._items: dict[str, tuple[Account, str]] = {}
        self._writes = writes

    async def add(self, account: Account, encrypted_password: str) -> None:
        self._writes.count += 1
        self._items[account.id] = (account, encrypted_password)

    async def list_all(self) -> list[Account]:
        return [account for account, _ in self._items.values()]

    async def get_with_secret(self, account_id: str) -> tuple[Account, str] | None:
        return self._items.get(account_id)

    async def delete(self, account_id: str) -> None:
        self._writes.count += 1
        self._items.pop(account_id, None)


class MemoryFavorites:
    def __init__(self, writes: "WriteCounter") -> None:
        self._items: dict[str, Favorite] = {}
        self._writes = writes

    async def add(self, favorite: Favorite) -> None:
        if favorite.id in self._items:
            raise KeyError(favorite.id)
        self._writes.count += 1
        self._items[favorite.id] = favorite

    async def get(self, favorite_id: str) -> Favorite | None:
        return self._items.get(favorite_id)

    async def list_all(self, account_id: str | None = None) -> list[Favorite]:
        return [f for f in self._items.values() if account_id in (None, f.account_id)]

    async def list_active(self) -> list[Favorite]:
        return [f for f in self._items.values() if f.state in ("watching", "purchasing")]

    async def update_settings(
        self, favorite_id: str, payment_method: str, price_cap_yen: int | None
    ) -> bool:
        current = self._items.get(favorite_id)
        if current is None:
            return False
        self._writes.count += 1
        self._items[favorite_id] = current.model_copy(
            update={"payment_method": payment_method, "price_cap_yen": price_cap_yen}
        )
        return True

    async def transition(
        self,
        favorite_id: str,
        current: FavoriteState,
        target: FavoriteState,
        expected_version: int,
        now: datetime,
    ) -> bool:
        item = self._items.get(favorite_id)
        if item is None or item.state != current or item.state_version != expected_version:
            return False
        self._writes.count += 1
        self._items[favorite_id] = item.model_copy(
            update={
                "state": target,
                "state_version": item.state_version + 1,
                "state_changed_at": now,
            }
        )
        return True

    async def delete(self, favorite_id: str) -> None:
        self._writes.count += 1
        self._items.pop(favorite_id, None)

    async def delete_for_account(self, account_id: str) -> None:
        for fid in [f.id for f in self._items.values() if f.account_id == account_id]:
            await self.delete(fid)


class MemoryNotifications:
    def __init__(self, writes: "WriteCounter") -> None:
        self._items: list[Notification] = []
        self._writes = writes

    async def add(self, notification: Notification) -> None:
        self._writes.count += 1
        self._items.append(notification)

    async def list_all(self, limit: int = 50) -> list[Notification]:
        return sorted(self._items, key=lambda n: n.created_at, reverse=True)[:limit]

    async def unread_count(self) -> int:
        return sum(1 for n in self._items if not n.read)

    async def mark_all_read(self) -> None:
        self._writes.count += 1
        self._items = [n.model_copy(update={"read": True}) for n in self._items]


class MemorySettings:
    def __init__(self, writes: "WriteCounter") -> None:
        self._enabled = True
        self._tick: datetime | None = None
        self._writes = writes

    async def auto_purchase_enabled(self) -> bool:
        return self._enabled

    async def set_auto_purchase_enabled(self, enabled: bool) -> None:
        self._writes.count += 1
        self._enabled = enabled

    async def last_tick_at(self) -> datetime | None:
        return self._tick

    async def record_tick(self, at: datetime) -> None:
        self._writes.count += 1
        self._tick = at


@dataclass
class WriteCounter:
    count: int = 0


@dataclass
class MemoryRepos:
    writes: WriteCounter = field(default_factory=WriteCounter)
    accounts: MemoryAccounts = field(init=False)
    favorites: MemoryFavorites = field(init=False)
    notifications: MemoryNotifications = field(init=False)
    settings: MemorySettings = field(init=False)

    def __post_init__(self) -> None:
        self.accounts = MemoryAccounts(self.writes)
        self.favorites = MemoryFavorites(self.writes)
        self.notifications = MemoryNotifications(self.writes)
        self.settings = MemorySettings(self.writes)
