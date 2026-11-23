from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Genre(BaseModel):
    """サイトのカテゴリ（ジャンル）。プルダウンの選択肢。"""

    model_config = ConfigDict(frozen=True)

    category_id: int
    label: str


# 実サイトで確認したカテゴリ（2026-11-23）。増減はここで行う。
GENRES: tuple[Genre, ...] = (
    Genre(category_id=22, label="SuperDollfie > 本体"),
    Genre(category_id=136, label="SDGIRL/SD13GIRL"),
    Genre(category_id=137, label="SDBOY/SD13BOY"),
    Genre(category_id=139, label="MSD"),
    Genre(category_id=140, label="幼SD"),
    Genre(category_id=138, label="DD"),
    Genre(category_id=47, label="ドルフィードリーム"),
    Genre(category_id=2, label="Blythe"),
)

DEFAULT_GENRE_ID = 22

_BY_ID = {g.category_id: g for g in GENRES}


def get_genre(category_id: int) -> Genre:
    return _BY_ID[category_id]


class KeywordFavorite(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    account_id: str
    keyword: str
    category_id: int
    category_label: str
    payment_method: str
    price_cap_yen: int | None
    enabled: bool
    new_arrival_count: int
    created_at: datetime
