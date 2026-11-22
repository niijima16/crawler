"""環境変数から、永続化・暗号化・時計などの実装を組み立てる（main.py とワーカーで共有する）。"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import NamedTuple

from spider.application.ports import (
    AccountRepository,
    FavoriteRepository,
    NotificationRepository,
    SecretBox,
    SettingsRepository,
)
from spider.infrastructure.dynamodb_repos import build_repositories, connect, ensure_tables
from spider.infrastructure.secret_box import FernetSecretBox

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_TABLE_PREFIX = "spider-"


class Store(NamedTuple):
    accounts: AccountRepository
    favorites: FavoriteRepository
    notifications: NotificationRepository
    settings: SettingsRepository
    secret_box: SecretBox


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


def build_store(env: Mapping[str, str]) -> tuple[Store, Callable[[], Awaitable[None]]]:
    """リポジトリ一式と、テーブルを作る（無ければ）起動時の処理を返す。"""
    key = env.get("CREDENTIALS_KEY")
    if not key:
        raise ValueError("CREDENTIALS_KEY（資格情報を暗号化する鍵）を環境変数で指定してください")
    secret_box = FernetSecretBox(key)  # 不正な鍵は ValueError
    client, resource = connect(env.get("DYNAMODB_ENDPOINT"), env.get("AWS_REGION", DEFAULT_REGION))
    prefix = env.get("TABLE_PREFIX", DEFAULT_TABLE_PREFIX)
    repos = build_repositories(resource, prefix)

    async def setup() -> None:
        await asyncio.to_thread(ensure_tables, client, prefix)

    return (
        Store(repos.accounts, repos.favorites, repos.notifications, repos.settings, secret_box),
        setup,
    )
