from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

from spider.domain.order import Order


def test_order_is_a_pydantic_model() -> None:
    assert issubclass(Order, BaseModel)


def test_order_is_immutable() -> None:
    order = Order(order_id="1", purchased_on=date(2026, 1, 1), total_yen=100)

    with pytest.raises(ValidationError):
        order.total_yen = 200


def test_orders_with_same_values_are_equal() -> None:
    a = Order(order_id="1", purchased_on=date(2026, 1, 1), total_yen=100)
    b = Order(order_id="1", purchased_on=date(2026, 1, 1), total_yen=100)

    assert a == b
