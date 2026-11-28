import re

from spider.application.ports import UpstreamError
from spider.application.use_cases import ProductNotFound
from spider.domain.keyword_favorite import Genre
from spider.domain.product import CheckoutPreview, OrderForm, ProductSummary
from spider.infrastructure.html_tree import Node, parse_html


def _yen(text: str) -> int:
    return int(re.sub(r"\D", "", text))


def _span(root: Node, cls: str) -> Node | None:
    return root.find(lambda n: n.tag == "span" and n.has_class(cls))


def _has_cart_form(root: Node, product_id: int) -> bool:
    select = root.find(
        lambda n: n.tag == "select" and n.attrs.get("name") == f"cart_addquantity_{product_id}"
    )
    return select is not None and select.find(lambda n: n.tag == "option") is not None


def extract_product_page(html: str, product_id: int) -> ProductSummary:
    root = parse_html(html)
    name = _span(root, "goods_name")
    price = root.find(lambda n: n.tag == "span" and n.attrs.get("id") == "pricech")
    if name is None or price is None:
        raise ProductNotFound
    return ProductSummary(
        product_id=product_id,
        name=name.text(),
        price_yen=_yen(price.text()),
        in_stock=_has_cart_form(root, product_id),
    )


def _category_id(href: str) -> int | None:
    match = re.search(r"/product-list/(\d+)", href)
    return int(match.group(1)) if match else None


def extract_categories(html: str) -> list[Genre]:
    """カテゴリのドロップダウン（親カテゴリ > 子カテゴリ）から Genre の一覧を作る。

    コメントアウトされた旧ブロックはパーサが破棄する。PC版・スマホ版で同じ id が重複
    するため、最初に出てきたものを採用して dedupe する。
    """
    root = parse_html(html)
    seen: set[int] = set()
    categories: list[Genre] = []
    for block in root.find_all(lambda n: n.tag == "li" and n.has_class("parent_category")):
        parent = block.find(lambda n: n.tag == "a" and n.has_class("parentcategory_link"))
        subs = block.find(lambda n: n.tag == "ul" and n.has_class("subcategories"))
        if parent is None or subs is None:
            continue
        parent_label = parent.text()
        for link in subs.find_all(lambda n: n.tag == "a"):
            category_id = _category_id(link.attrs.get("href", ""))
            child_label = link.text()
            if category_id is None or category_id in seen or not child_label:
                continue
            seen.add(category_id)
            categories.append(
                Genre(category_id=category_id, label=f"{parent_label} > {child_label}")
            )
    return categories


def extract_product_ids(html: str) -> set[int]:
    root = parse_html(html)
    return {
        int(n.attrs["data-product-id"])
        for n in root.find_all(lambda n: n.tag == "div" and "data-product-id" in n.attrs)
    }


def extract_search_results(html: str, in_stock_ids: set[int]) -> list[ProductSummary]:
    root = parse_html(html)
    results: list[ProductSummary] = []
    for cell in root.find_all(lambda n: n.tag == "li" and n.has_class("list_item_cell")):
        data = cell.find(lambda n: "data-product-id" in n.attrs)
        name = _span(cell, "goods_name")
        price = _span(cell, "figure")
        if data is None or name is None or price is None:
            continue
        product_id = int(data.attrs["data-product-id"])
        results.append(
            ProductSummary(
                product_id=product_id,
                name=name.text(),
                price_yen=_yen(price.text()),
                in_stock=product_id in in_stock_ids,
            )
        )
    return results


def extract_payment_options(html: str) -> dict[str, str]:
    root = parse_html(html)
    labels = {
        n.attrs["for"]: n.text()
        for n in root.find_all(lambda n: n.tag == "label" and "for" in n.attrs)
    }
    return {
        radio.attrs["value"]: labels.get(radio.attrs.get("id", ""), "")
        for radio in root.find_all(
            lambda n: (
                n.tag == "input"
                and n.attrs.get("name") == "pay_procedure"
                and n.attrs.get("type") == "radio"
            )
        )
    }


def extract_confirm(html: str, product_id: int) -> CheckoutPreview:
    root = parse_html(html)
    name = _span(root, "goods_name")
    fee = _span(root, "grandchargel_price")
    total = _span(root, "grandtotal_price")
    payment_box = root.find(lambda n: n.tag == "div" and n.has_class("disp_payment_method"))
    payment = (
        payment_box.find(lambda n: n.tag == "div" and n.has_class("disp_customer_txt"))
        if payment_box
        else None
    )
    if name is None or fee is None or total is None or payment is None:
        raise UpstreamError
    return CheckoutPreview(
        product_id=product_id,
        item_name=name.text(),
        payment_method=payment.text(),
        shipping_fee_yen=_yen(fee.text()),
        total_yen=_yen(total.text()),
    )


def extract_order_form(html: str) -> OrderForm:
    root = parse_html(html)
    for form in root.find_all(lambda n: n.tag == "form" and "action" in n.attrs):
        inputs = list(form.find_all(lambda n: n.tag == "input"))
        if not any(
            i.attrs.get("name") == "go-next" and i.attrs.get("type") == "submit" for i in inputs
        ):
            continue
        fields: dict[str, str] = {}
        for i in inputs:
            name, kind = i.attrs.get("name", ""), i.attrs.get("type", "")
            if kind == "hidden" or (kind == "checkbox" and name == "policy_agree"):
                fields[name] = i.attrs.get("value", "1")
            elif kind == "submit" and name == "go-next":
                fields[name] = i.attrs.get("value", "")
        return OrderForm(action=form.attrs["action"], fields=fields)
    raise UpstreamError


def is_recaptcha_rejected(html: str) -> bool:
    return "reCAPTCHAの検証に失敗" in html


def is_in_cart(html: str, product_id: int) -> bool:
    root = parse_html(html)
    return (
        root.find(lambda n: n.tag == "input" and n.attrs.get("name") == f"cart_remove_{product_id}")
        is not None
    )
