import pytest
from pydantic import ValidationError

from spider.domain.payment import DEFAULT_PAYMENT_METHOD_ID, PAYMENT_METHODS, get_payment_method
from spider.domain.product import CheckoutPreview, OrderResult, ProductSummary


def test_all_eight_payment_methods_are_defined() -> None:
    assert {m.id: m.label for m in PAYMENT_METHODS} == {
        "3": "代金引換",
        "1": "銀行振込",
        "2": "郵便振替",
        "10000006": "PayPal",
        "10000028": "クレジットカード",
        "10000002_1": "後払い",
        "8": "店頭支払",
        "10000050": "PayPayオンライン",
    }


def test_default_is_store_payment() -> None:
    assert DEFAULT_PAYMENT_METHOD_ID == "8"
    assert get_payment_method("8").label == "店頭支払"


def test_credit_card_cannot_be_previewed() -> None:
    card = get_payment_method("10000028")

    assert not card.preview_supported
    assert not card.submit_supported


@pytest.mark.parametrize("method_id", ["8", "3", "1", "2"])
def test_on_site_methods_support_order_submission(method_id: str) -> None:
    method = get_payment_method(method_id)

    assert method.preview_supported
    assert method.submit_supported


@pytest.mark.parametrize("method_id", ["10000006", "10000050", "10000002_1"])
def test_external_methods_are_preview_only(method_id: str) -> None:
    method = get_payment_method(method_id)

    assert method.preview_supported
    assert not method.submit_supported


def test_unknown_payment_method_is_rejected() -> None:
    with pytest.raises(KeyError):
        get_payment_method("999")


def test_value_objects_are_immutable() -> None:
    product = ProductSummary(product_id=1, name="n", price_yen=100, in_stock=True)
    preview = CheckoutPreview(
        product_id=1, item_name="n", payment_method="店頭支払", shipping_fee_yen=660, total_yen=760
    )
    order = OrderResult(status="rejected", order_id=None, reason="recaptcha")

    for value, field in ((product, "name"), (preview, "total_yen"), (order, "status")):
        with pytest.raises(ValidationError):
            setattr(value, field, "x")
