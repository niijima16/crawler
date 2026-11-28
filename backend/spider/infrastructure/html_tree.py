import re
from collections.abc import Callable, Iterator
from html.parser import HTMLParser

_VOID = {"input", "img", "br", "wbr", "meta", "link", "hr"}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None") -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Node | str] = []

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def descendants(self) -> Iterator["Node"]:
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()

    def find_all(self, predicate: Callable[["Node"], bool]) -> Iterator["Node"]:
        return (node for node in self.descendants() if predicate(node))

    def find(self, predicate: Callable[["Node"], bool]) -> "Node | None":
        return next(self.find_all(predicate), None)

    def text(self) -> str:
        parts = [c if isinstance(c, str) else c.text() for c in self.children]
        return re.sub(r"\s+", " ", "".join(parts)).strip()


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = Node("#root", {}, None)
        self._current = self.root

    def _new(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node:
        node = Node(tag, {k: v or "" for k, v in attrs}, self._current)
        self._current.children.append(node)
        return node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = self._new(tag, attrs)
        if tag not in _VOID:
            self._current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._new(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        node: Node | None = self._current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self._current = node.parent

    def handle_data(self, data: str) -> None:
        self._current.children.append(data)


def parse_html(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    return builder.root
