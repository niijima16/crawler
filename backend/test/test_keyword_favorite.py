from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spider.domain.account import Notification
from spider.domain.keyword_favorite import (
    DEFAULT_GENRE_ID,
    GENRES,
    KeywordFavorite,
    get_genre,
)

NOW = datetime(2026, 11, 23, 21, 0, tzinfo=UTC)


def test_default_genre_is_superdollfie_body() -> None:
    assert DEFAULT_GENRE_ID == 22
    assert get_genre(22).label == "SuperDollfie > 本体"


def test_genres_are_defined_and_unique() -> None:
    ids = [g.category_id for g in GENRES]
    assert len(ids) == len(set(ids))
    assert 22 in ids
    assert len(GENRES) >= 8


def test_an_unknown_genre_is_rejected() -> None:
    with pytest.raises(KeyError):
        get_genre(999999)


def test_keyword_favorite_is_immutable() -> None:
    favorite = KeywordFavorite(
        id="k1",
        account_id="a1",
        keyword="豆本",
        category_id=22,
        category_label="SuperDollfie > 本体",
        payment_method="8",
        price_cap_yen=None,
        enabled=True,
        new_arrival_count=0,
        created_at=NOW,
    )

    with pytest.raises(ValidationError):
        favorite.keyword = "x"


def test_notification_carries_product_and_payment_for_new_arrivals() -> None:
    note = Notification(
        id="n1",
        favorite_id="k1",
        kind="new_arrival",
        message="m",
        created_at=NOW,
        read=False,
        product_id=807736,
        payment_method="8",
    )

    assert note.product_id == 807736
    assert note.payment_method == "8"


def test_notification_product_and_payment_default_to_none() -> None:
    note = Notification(
        id="n2", favorite_id=None, kind="purchased", message="m", created_at=NOW, read=False
    )

    assert note.product_id is None
    assert note.payment_method is None
