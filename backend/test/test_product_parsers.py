from pathlib import Path

import pytest

from spider.application.use_cases import ProductNotFound
from spider.domain.product import CheckoutPreview, OrderForm, ProductSummary
from spider.infrastructure.product_parsers import (
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    extract_product_ids,
    extract_product_page,
    extract_search_results,
    is_in_cart,
    is_recaptcha_rejected,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_product_page_purchasable() -> None:
    summary = extract_product_page(_html("product_page_purchasable.html"), 810297)

    assert summary == ProductSummary(
        product_id=810297, name="SD/豆本 I-26-11-05-335-KD-ZI", price_yen=550, in_stock=True
    )


def test_product_page_soldout_has_no_cart_form() -> None:
    summary = extract_product_page(_html("product_page_soldout.html"), 810296)

    assert summary.in_stock is False
    assert summary.price_yen == 550


def test_product_page_without_name_raises() -> None:
    with pytest.raises(ProductNotFound):
        extract_product_page("<html><body>nothing</body></html>", 1)


def test_search_results_keep_the_whole_name_despite_nested_emphasis() -> None:
    html = _html("product_list_keyword.html")
    in_stock = extract_product_ids(_html("product_list_keyword_available.html"))

    results = extract_search_results(html, in_stock)

    assert results == [
        ProductSummary(
            product_id=775386, name="SD/豆本 S-26-08-09-376-TO-ZS", price_yen=440, in_stock=True
        ),
        ProductSummary(
            product_id=810296, name="SD/豆本 I-26-11-05-334-KD-ZI", price_yen=550, in_stock=False
        ),
        ProductSummary(
            product_id=810297, name="SD/豆本 I-26-11-05-335-KD-ZI", price_yen=550, in_stock=True
        ),
    ]


def test_search_with_no_items_is_empty() -> None:
    assert extract_search_results("<html><body>0件</body></html>", set()) == []
    assert extract_product_ids("<html></html>") == set()


def test_payment_options_lists_every_radio() -> None:
    options = extract_payment_options(_html("cart_shipping.html"))

    assert options["8"] == "店頭支払"
    assert options["10000002_1"] == "後払い"
    assert len(options) == 8


def test_payment_options_without_store_payment() -> None:
    assert "8" not in extract_payment_options(_html("cart_shipping_no_pickup.html"))


def test_confirm_page_summary() -> None:
    preview = extract_confirm(_html("cart_confirm.html"), 769926)

    assert preview == CheckoutPreview(
        product_id=769926,
        item_name="SD16/OF:靴 U-26-07-22-192-TN-ZU",
        payment_method="店頭支払",
        shipping_fee_yen=660,
        total_yen=3740,
    )


def test_order_form_has_action_and_required_fields_only() -> None:
    form = extract_order_form(_html("cart_confirm.html"))

    assert form == OrderForm(
        action="https://www.dollyteria.com/cart/confirm",
        fields={"coupon_use": "f", "policy_agree": "1", "go-next": "購入する"},
    )


def test_recaptcha_rejection_is_detected() -> None:
    assert is_recaptcha_rejected(_html("cart_confirm_recaptcha_failed.html"))
    assert not is_recaptcha_rejected(_html("cart_confirm.html"))


def test_item_is_in_cart_when_the_remove_button_exists() -> None:
    assert is_in_cart(_html("cart_with_item.html"), 769926)
    assert not is_in_cart(_html("cart_with_item.html"), 1)


def test_sold_out_product_page_is_not_a_cart_page() -> None:
    assert not is_in_cart(_html("product_page_soldout.html"), 810296)
