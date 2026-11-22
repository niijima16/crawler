from pathlib import Path

import pytest

from spider.application.use_cases import ProductNotFound
from spider.infrastructure.product_parser import extract_latest_product_name

FIXTURES = Path(__file__).parent / "fixtures"


def test_returns_first_goods_name() -> None:
    html = (FIXTURES / "product_list_new.html").read_text(encoding="utf-8")

    assert extract_latest_product_name(html) == "MSD/健 I-26-11-19-382-KD-ZI"


def test_raises_when_no_goods_name() -> None:
    with pytest.raises(ProductNotFound):
        extract_latest_product_name("<html><body><p>empty</p></body></html>")
