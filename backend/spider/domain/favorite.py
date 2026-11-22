from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

FavoriteState = Literal["watching", "purchasing", "purchased", "rejected", "unknown", "stopped"]

# 終了状態（purchased, rejected, unknown, stopped）からは、ユーザー操作で watching に戻すだけ。
_ALLOWED: dict[FavoriteState, frozenset[FavoriteState]] = {
    "watching": frozenset({"purchasing", "stopped"}),
    "purchasing": frozenset({"purchased", "rejected", "unknown", "stopped", "watching"}),
    "purchased": frozenset({"watching"}),
    "rejected": frozenset({"watching"}),
    "unknown": frozenset({"watching"}),
    "stopped": frozenset({"watching"}),
}


def can_transition(current: FavoriteState, target: FavoriteState) -> bool:
    return target in _ALLOWED[current]


class Favorite(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    account_id: str
    product_id: int
    product_name: str
    payment_method: str
    price_cap_yen: int | None
    state: FavoriteState
    state_version: int
    state_changed_at: datetime
