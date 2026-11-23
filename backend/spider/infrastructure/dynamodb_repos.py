"""DynamoDB（オンデマンド課金）によるリポジトリ。書き込みは、ユーザー操作と状態遷移のときだけ行う。"""

import asyncio
from datetime import UTC, datetime
from typing import Any, NamedTuple

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from botocore.exceptions import ClientError

from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite, FavoriteState
from spider.domain.keyword_favorite import KeywordFavorite

_CLIENT_CONFIG = Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 3})

_TABLES: dict[str, list[tuple[str, str]]] = {
    "accounts": [("id", "HASH")],
    "favorites": [("id", "HASH")],
    "notifications": [("pk", "HASH"), ("sk", "RANGE")],
    "settings": [("id", "HASH")],
    "keyword_favorites": [("id", "HASH")],
}
_NOTIFICATION_PARTITION = "N"
_SETTINGS_ID = "settings"


def connect(endpoint_url: str | None, region: str) -> tuple[Any, Any]:
    """DynamoDB の client と resource を作る。ローカルは endpoint_url を指定する。"""
    options: dict[str, Any] = {"region_name": region, "config": _CLIENT_CONFIG}
    if endpoint_url:
        options["endpoint_url"] = endpoint_url
        # DynamoDB Local は任意の資格情報を受け付ける
        options["aws_access_key_id"] = "local"
        options["aws_secret_access_key"] = "local"
    return boto3.client("dynamodb", **options), boto3.resource("dynamodb", **options)


def ensure_tables(client: Any, prefix: str) -> None:
    """テーブルが無ければ作る（あれば何もしない）。"""
    for name, keys in _TABLES.items():
        table_name = f"{prefix}{name}"
        try:
            client.create_table(
                TableName=table_name,
                KeySchema=[{"AttributeName": a, "KeyType": t} for a, t in keys],
                AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a, _ in keys],
                BillingMode="PAY_PER_REQUEST",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceInUseException":
                raise
        client.get_waiter("table_exists").wait(
            TableName=table_name, WaiterConfig={"Delay": 0.2, "MaxAttempts": 150}
        )


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _items(table: Any, method: str, **kwargs: Any) -> list[dict[str, Any]]:
    """scan / query のページを最後まで読む。"""
    items: list[dict[str, Any]] = []
    while True:
        response = getattr(table, method)(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return items
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


class DynamoAccounts:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def add(self, account: Account, encrypted_password: str) -> None:
        item = {**account.model_dump(), "password_enc": encrypted_password}
        await asyncio.to_thread(self._table.put_item, Item=item)

    async def list_all(self) -> list[Account]:
        items = await asyncio.to_thread(_items, self._table, "scan")
        return [Account(id=i["id"], label=i["label"], email=i["email"]) for i in items]

    async def get_with_secret(self, account_id: str) -> tuple[Account, str] | None:
        if not account_id:  # DynamoDB は空文字のキーを受け付けない
            return None
        response = await asyncio.to_thread(self._table.get_item, Key={"id": account_id})
        item = response.get("Item")
        if item is None:
            return None
        return Account(id=item["id"], label=item["label"], email=item["email"]), item[
            "password_enc"
        ]

    async def delete(self, account_id: str) -> None:
        if account_id:
            await asyncio.to_thread(self._table.delete_item, Key={"id": account_id})


def _favorite_to_item(favorite: Favorite) -> dict[str, Any]:
    item = favorite.model_dump(exclude={"price_cap_yen", "state_changed_at"})
    item["state_changed_at"] = _iso(favorite.state_changed_at)
    if favorite.price_cap_yen is not None:
        item["price_cap_yen"] = favorite.price_cap_yen
    return item


def _favorite_from_item(item: dict[str, Any]) -> Favorite:
    cap = item.get("price_cap_yen")
    return Favorite(
        id=item["id"],
        account_id=item["account_id"],
        product_id=int(item["product_id"]),
        product_name=item["product_name"],
        payment_method=item["payment_method"],
        price_cap_yen=int(cap) if cap is not None else None,
        state=item["state"],
        state_version=int(item["state_version"]),
        state_changed_at=datetime.fromisoformat(item["state_changed_at"]),
    )


def _condition_failed(error: ClientError) -> bool:
    return str(error.response["Error"]["Code"]) == "ConditionalCheckFailedException"


class DynamoFavorites:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def add(self, favorite: Favorite) -> None:
        await asyncio.to_thread(
            self._table.put_item,
            Item=_favorite_to_item(favorite),
            ConditionExpression=Attr("id").not_exists(),
        )

    async def get(self, favorite_id: str) -> Favorite | None:
        if not favorite_id:
            return None
        response = await asyncio.to_thread(self._table.get_item, Key={"id": favorite_id})
        item = response.get("Item")
        return _favorite_from_item(item) if item else None

    async def list_all(self, account_id: str | None = None) -> list[Favorite]:
        kwargs: dict[str, Any] = {}
        if account_id is not None:
            kwargs["FilterExpression"] = Attr("account_id").eq(account_id)
        items = await asyncio.to_thread(_items, self._table, "scan", **kwargs)
        return sorted((_favorite_from_item(i) for i in items), key=lambda f: f.state_changed_at)

    async def list_active(self) -> list[Favorite]:
        items = await asyncio.to_thread(
            _items,
            self._table,
            "scan",
            FilterExpression=Attr("state").is_in(["watching", "purchasing"]),
        )
        return [_favorite_from_item(i) for i in items]

    async def update_settings(
        self, favorite_id: str, payment_method: str, price_cap_yen: int | None
    ) -> bool:
        if not favorite_id:
            return False
        expression = "SET payment_method = :p"
        values: dict[str, Any] = {":p": payment_method}
        if price_cap_yen is None:
            expression += " REMOVE price_cap_yen"
        else:
            expression += ", price_cap_yen = :c"
            values[":c"] = price_cap_yen
        try:
            await asyncio.to_thread(
                self._table.update_item,
                Key={"id": favorite_id},
                UpdateExpression=expression,
                ConditionExpression=Attr("id").exists(),
                ExpressionAttributeValues=values,
            )
        except ClientError as error:
            if _condition_failed(error):
                return False
            raise
        return True

    async def transition(
        self,
        favorite_id: str,
        current: FavoriteState,
        target: FavoriteState,
        expected_version: int,
        now: datetime,
    ) -> bool:
        if not favorite_id:
            return False
        try:
            await asyncio.to_thread(
                self._table.update_item,
                Key={"id": favorite_id},
                UpdateExpression=(
                    "SET #s = :target, state_version = state_version + :one, "
                    "state_changed_at = :now"
                ),
                ConditionExpression="#s = :current AND state_version = :version",
                ExpressionAttributeNames={"#s": "state"},
                ExpressionAttributeValues={
                    ":target": target,
                    ":current": current,
                    ":version": expected_version,
                    ":one": 1,
                    ":now": _iso(now),
                },
            )
        except ClientError as error:
            if _condition_failed(error):
                return False
            raise
        return True

    async def delete(self, favorite_id: str) -> None:
        if favorite_id:
            await asyncio.to_thread(self._table.delete_item, Key={"id": favorite_id})

    async def delete_for_account(self, account_id: str) -> None:
        for favorite in await self.list_all(account_id):
            await self.delete(favorite.id)


class DynamoNotifications:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def add(self, notification: Notification) -> None:
        item: dict[str, Any] = {
            "pk": _NOTIFICATION_PARTITION,
            "sk": f"{_iso(notification.created_at)}#{notification.id}",
            "id": notification.id,
            "kind": notification.kind,
            "message": notification.message,
            "created_at": _iso(notification.created_at),
            "read": notification.read,
        }
        if notification.favorite_id is not None:
            item["favorite_id"] = notification.favorite_id
        if notification.product_id is not None:
            item["product_id"] = notification.product_id
        if notification.payment_method is not None:
            item["payment_method"] = notification.payment_method
        await asyncio.to_thread(self._table.put_item, Item=item)

    async def list_all(self, limit: int = 50) -> list[Notification]:
        response = await asyncio.to_thread(
            self._table.query,
            KeyConditionExpression=Key("pk").eq(_NOTIFICATION_PARTITION),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [
            Notification(
                id=i["id"],
                favorite_id=i.get("favorite_id"),
                kind=i["kind"],
                message=i["message"],
                created_at=datetime.fromisoformat(i["created_at"]),
                read=bool(i["read"]),
                product_id=int(i["product_id"]) if i.get("product_id") is not None else None,
                payment_method=i.get("payment_method"),
            )
            for i in response["Items"]
        ]

    async def _unread_keys(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            _items,
            self._table,
            "query",
            KeyConditionExpression=Key("pk").eq(_NOTIFICATION_PARTITION),
            FilterExpression=Attr("read").eq(False),
            ProjectionExpression="pk, sk",
        )

    async def unread_count(self) -> int:
        return len(await self._unread_keys())

    async def mark_all_read(self) -> None:
        for key in await self._unread_keys():
            await asyncio.to_thread(
                self._table.update_item,
                Key={"pk": key["pk"], "sk": key["sk"]},
                UpdateExpression="SET #r = :true",
                ExpressionAttributeNames={"#r": "read"},
                ExpressionAttributeValues={":true": True},
            )


class DynamoSettings:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def _item(self) -> dict[str, Any]:
        response = await asyncio.to_thread(self._table.get_item, Key={"id": _SETTINGS_ID})
        return dict(response.get("Item", {}))

    async def auto_purchase_enabled(self) -> bool:
        return bool((await self._item()).get("auto_purchase_enabled", True))

    async def set_auto_purchase_enabled(self, enabled: bool) -> None:
        await asyncio.to_thread(
            self._table.update_item,
            Key={"id": _SETTINGS_ID},
            UpdateExpression="SET auto_purchase_enabled = :e",
            ExpressionAttributeValues={":e": enabled},
        )

    async def last_tick_at(self) -> datetime | None:
        value = (await self._item()).get("last_tick_at")
        return datetime.fromisoformat(value) if value else None

    async def record_tick(self, at: datetime) -> None:
        await asyncio.to_thread(
            self._table.update_item,
            Key={"id": _SETTINGS_ID},
            UpdateExpression="SET last_tick_at = :t",
            ExpressionAttributeValues={":t": _iso(at)},
        )


class DynamoKeywordFavorites:
    def __init__(self, table: Any) -> None:
        self._table = table

    def _to_item(self, favorite: KeywordFavorite) -> dict[str, Any]:
        item = favorite.model_dump(exclude={"price_cap_yen", "created_at"})
        item["created_at"] = _iso(favorite.created_at)
        if favorite.price_cap_yen is not None:
            item["price_cap_yen"] = favorite.price_cap_yen
        return item

    def _from_item(self, i: dict[str, Any]) -> KeywordFavorite:
        cap = i.get("price_cap_yen")
        return KeywordFavorite(
            id=i["id"],
            account_id=i["account_id"],
            keyword=i["keyword"],
            category_id=int(i["category_id"]),
            category_label=i["category_label"],
            payment_method=i["payment_method"],
            price_cap_yen=int(cap) if cap is not None else None,
            enabled=bool(i["enabled"]),
            new_arrival_count=int(i["new_arrival_count"]),
            created_at=datetime.fromisoformat(i["created_at"]),
        )

    async def add(
        self, favorite: KeywordFavorite, seen_product_ids: set[int] | None = None
    ) -> None:
        item = self._to_item(favorite)
        if seen_product_ids:
            item["seen_product_ids"] = set(seen_product_ids)
        await asyncio.to_thread(
            self._table.put_item,
            Item=item,
            ConditionExpression=Attr("id").not_exists(),
        )

    async def get(self, favorite_id: str) -> KeywordFavorite | None:
        if not favorite_id:
            return None
        response = await asyncio.to_thread(self._table.get_item, Key={"id": favorite_id})
        item = response.get("Item")
        return self._from_item(item) if item else None

    async def list_all(self, account_id: str | None = None) -> list[KeywordFavorite]:
        kwargs: dict[str, Any] = {}
        if account_id is not None:
            kwargs["FilterExpression"] = Attr("account_id").eq(account_id)
        items = await asyncio.to_thread(_items, self._table, "scan", **kwargs)
        return [self._from_item(i) for i in items]

    async def list_enabled(self) -> list[KeywordFavorite]:
        items = await asyncio.to_thread(
            _items, self._table, "scan", FilterExpression=Attr("enabled").eq(True)
        )
        return [self._from_item(i) for i in items]

    async def update_settings(
        self, favorite_id: str, payment_method: str, price_cap_yen: int | None
    ) -> bool:
        expression = "SET payment_method = :p"
        values: dict[str, Any] = {":p": payment_method}
        if price_cap_yen is None:
            expression += " REMOVE price_cap_yen"
        else:
            expression += ", price_cap_yen = :c"
            values[":c"] = price_cap_yen
        return await self._update(favorite_id, expression, values)

    async def set_enabled(self, favorite_id: str, enabled: bool) -> bool:
        return await self._update(favorite_id, "SET enabled = :e", {":e": enabled})

    async def _update(self, favorite_id: str, expression: str, values: dict[str, Any]) -> bool:
        if not favorite_id:
            return False
        try:
            await asyncio.to_thread(
                self._table.update_item,
                Key={"id": favorite_id},
                UpdateExpression=expression,
                ConditionExpression=Attr("id").exists(),
                ExpressionAttributeValues=values,
            )
        except ClientError as error:
            if _condition_failed(error):
                return False
            raise
        return True

    async def delete(self, favorite_id: str) -> None:
        if favorite_id:
            await asyncio.to_thread(self._table.delete_item, Key={"id": favorite_id})

    async def delete_for_account(self, account_id: str) -> None:
        for favorite in await self.list_all(account_id):
            await self.delete(favorite.id)

    async def claim_product(self, favorite_id: str, product_id: int) -> bool:
        if not favorite_id:
            return False
        try:
            await asyncio.to_thread(
                self._table.update_item,
                Key={"id": favorite_id},
                UpdateExpression="ADD seen_product_ids :p",
                ConditionExpression=(
                    "attribute_not_exists(seen_product_ids) OR NOT contains(seen_product_ids, :pid)"
                ),
                ExpressionAttributeValues={":p": {product_id}, ":pid": product_id},
            )
        except ClientError as error:
            if _condition_failed(error):
                return False
            raise
        return True

    async def bump_new_arrival(self, favorite_id: str) -> None:
        await asyncio.to_thread(
            self._table.update_item,
            Key={"id": favorite_id},
            UpdateExpression="SET new_arrival_count = new_arrival_count + :one",
            ExpressionAttributeValues={":one": 1},
        )


class DynamoRepositories(NamedTuple):
    accounts: DynamoAccounts
    favorites: DynamoFavorites
    notifications: DynamoNotifications
    settings: DynamoSettings
    keyword_favorites: DynamoKeywordFavorites


def build_repositories(resource: Any, prefix: str) -> DynamoRepositories:
    def table(name: str) -> Any:
        return resource.Table(f"{prefix}{name}")

    return DynamoRepositories(
        accounts=DynamoAccounts(table("accounts")),
        favorites=DynamoFavorites(table("favorites")),
        notifications=DynamoNotifications(table("notifications")),
        settings=DynamoSettings(table("settings")),
        keyword_favorites=DynamoKeywordFavorites(table("keyword_favorites")),
    )
