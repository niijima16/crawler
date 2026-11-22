from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProductSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: int
    name: str
    price_yen: int
    in_stock: bool


class CheckoutPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: int
    item_name: str
    payment_method: str
    shipping_fee_yen: int
    total_yen: int


class OrderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["submitted", "rejected", "unknown"]
    order_id: str | None = None
    reason: str | None = None


class OrderForm(BaseModel):
    """確認画面の注文確定フォーム（送信先と送るフィールド）。"""

    model_config = ConfigDict(frozen=True)

    action: str
    fields: dict[str, str]


class StorePickupResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    preview: CheckoutPreview
    attempts: int
    order: OrderResult | None = None
