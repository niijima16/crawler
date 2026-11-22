from html.parser import HTMLParser

from spider.application.use_cases import ProductNotFound


class _Done(Exception):
    pass


class _FirstGoodsName(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "span" and ("class", "goods_name") in attrs:
            self._inside = True

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._inside and tag == "span":
            raise _Done

    @property
    def name(self) -> str:
        return "".join(self._parts).strip()


def extract_latest_product_name(html: str) -> str:
    parser = _FirstGoodsName()
    try:
        parser.feed(html)
    except _Done:
        return parser.name
    raise ProductNotFound
