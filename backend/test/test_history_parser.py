from datetime import date
from pathlib import Path

from spider.domain.order import Order
from spider.infrastructure.history_parser import extract_orders

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_orders_in_display_order() -> None:
    html = (FIXTURES / "sales_history.html").read_text(encoding="utf-8")

    orders = extract_orders(html)

    assert orders == [
        Order(order_id="96235", purchased_on=date(2026, 10, 21), total_yen=2860),
        Order(order_id="96230", purchased_on=date(2026, 10, 21), total_yen=2860),
        Order(order_id="95856", purchased_on=date(2026, 10, 14), total_yen=14300),
    ]


def test_returns_empty_list_when_no_orders() -> None:
    html = (FIXTURES / "sales_history_empty.html").read_text(encoding="utf-8")

    assert extract_orders(html) == []
