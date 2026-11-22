import re
from datetime import date
from html.parser import HTMLParser

from spider.domain.order import Order

_FIELDS = {"history_purchase_date", "history_id", "price"}


class _Orders(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.orders: list[Order] = []
        self._in_grand_total = False
        self._field: str | None = None
        self._depth = 0
        self._text: list[str] = []
        self._date = ""
        self._id = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "grand_total" in classes:
            self._in_grand_total = True
        if self._field is not None:
            if tag == "span":
                self._depth += 1
        elif tag == "span":
            for name in _FIELDS.intersection(classes):
                if name != "price" or self._in_grand_total:
                    self._field, self._depth, self._text = name, 1, []

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            self._in_grand_total = False
        if self._field is None or tag != "span":
            return
        self._depth -= 1
        if self._depth:
            return
        text = "".join(self._text)
        if self._field == "history_purchase_date":
            self._date = text
        elif self._field == "history_id":
            self._id = text
        else:
            self.orders.append(_build_order(self._id, self._date, text))
        self._field = None


def _build_order(order_id: str, purchased: str, price: str) -> Order:
    year, month, day = map(int, re.findall(r"\d+", purchased))
    return Order(
        order_id=order_id,
        purchased_on=date(year, month, day),
        total_yen=int(re.sub(r"\D", "", price)),
    )


def extract_orders(html: str) -> list[Order]:
    parser = _Orders()
    parser.feed(html)
    return parser.orders
