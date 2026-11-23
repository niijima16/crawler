"""環境変数から、永続化・暗号化・時計などの実装を組み立てる（main.py とワーカーで共有する）。"""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from spider.application.ports import (
    AccountRepository,
    FavoriteRepository,
    KeywordFavoriteRepository,
    NotificationRepository,
    SecretBox,
    SettingsRepository,
)
from spider.infrastructure.dynamodb_repos import build_repositories, connect, ensure_tables
from spider.infrastructure.secret_box import FernetSecretBox, generate_key

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_TABLE_PREFIX = "spider-"


class Store(NamedTuple):
    accounts: AccountRepository
    favorites: FavoriteRepository
    notifications: NotificationRepository
    settings: SettingsRepository
    keyword_favorites: KeywordFavoriteRepository
    secret_box: SecretBox


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


def _key_from_file(path: str | None) -> str | None:
    """ローカル用: 鍵ファイルを読む。無ければ作る（同時に起動した複数のサービスも同じ鍵になる）。"""
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write(generate_key())
        try:
            os.link(temporary, target)  # すでにあれば（別のサービスが先に作った）FileExistsError
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
    return target.read_text().strip()


def build_store(env: Mapping[str, str]) -> tuple[Store, Callable[[], Awaitable[None]]]:
    """リポジトリ一式と、テーブルを作る（無ければ）起動時の処理を返す。"""
    key = env.get("CREDENTIALS_KEY") or _key_from_file(env.get("CREDENTIALS_KEY_FILE"))
    if not key:
        raise ValueError(
            "CREDENTIALS_KEY（資格情報を暗号化する鍵）を環境変数で指定してください"
            "（ローカルでは CREDENTIALS_KEY_FILE で自動生成もできます）"
        )
    secret_box = FernetSecretBox(key)  # 不正な鍵は ValueError
    client, resource = connect(env.get("DYNAMODB_ENDPOINT"), env.get("AWS_REGION", DEFAULT_REGION))
    prefix = env.get("TABLE_PREFIX", DEFAULT_TABLE_PREFIX)
    repos = build_repositories(resource, prefix)

    async def setup() -> None:
        await asyncio.to_thread(ensure_tables, client, prefix)

    return (
        Store(
            repos.accounts,
            repos.favorites,
            repos.notifications,
            repos.settings,
            repos.keyword_favorites,
            secret_box,
        ),
        setup,
    )
