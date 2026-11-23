from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

NotificationKind = Literal[
    "purchased",
    "rejected",
    "unknown",
    "skipped_price_cap",
    "account_stopped",
    "submit_disabled",
    "new_arrival",
]


class Account(BaseModel):
    """サイトのアカウント。パスワードは持たない（暗号化した形でリポジトリだけが保持する）。"""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    email: str


class Notification(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    favorite_id: str | None
    kind: NotificationKind
    message: str
    created_at: datetime
    read: bool
    product_id: int | None = None
    payment_method: str | None = None
