from pydantic import BaseModel, ConfigDict


class PaymentMethod(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    preview_supported: bool
    submit_supported: bool


# サイトの配送画面の支払方法（観測値: 2026-11-22）。注文確定は、サイト内で完結する4種類のみ。
PAYMENT_METHODS: tuple[PaymentMethod, ...] = (
    PaymentMethod(id="8", label="店頭支払", preview_supported=True, submit_supported=True),
    PaymentMethod(id="3", label="代金引換", preview_supported=True, submit_supported=True),
    PaymentMethod(id="1", label="銀行振込", preview_supported=True, submit_supported=True),
    PaymentMethod(id="2", label="郵便振替", preview_supported=True, submit_supported=True),
    PaymentMethod(id="10000006", label="PayPal", preview_supported=True, submit_supported=False),
    PaymentMethod(
        id="10000050", label="PayPayオンライン", preview_supported=True, submit_supported=False
    ),
    PaymentMethod(id="10000002_1", label="後払い", preview_supported=True, submit_supported=False),
    PaymentMethod(
        id="10000028", label="クレジットカード", preview_supported=False, submit_supported=False
    ),
)

DEFAULT_PAYMENT_METHOD_ID = "8"

_BY_ID = {m.id: m for m in PAYMENT_METHODS}


def get_payment_method(method_id: str) -> PaymentMethod:
    return _BY_ID[method_id]
