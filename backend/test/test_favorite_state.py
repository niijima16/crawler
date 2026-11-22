from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite, FavoriteState, can_transition

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

STATES: list[FavoriteState] = [
    "watching",
    "purchasing",
    "purchased",
    "rejected",
    "unknown",
    "stopped",
]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("watching", "purchasing"),
        ("watching", "stopped"),
        ("purchasing", "purchased"),
        ("purchasing", "rejected"),
        ("purchasing", "unknown"),
        ("purchasing", "stopped"),
        ("purchasing", "watching"),
        ("purchased", "watching"),
        ("rejected", "watching"),
        ("unknown", "watching"),
        ("stopped", "watching"),
    ],
)
def test_allowed_transitions(current: FavoriteState, target: FavoriteState) -> None:
    assert can_transition(current, target)


def test_every_other_transition_is_rejected() -> None:
    allowed = {
        ("watching", "purchasing"),
        ("watching", "stopped"),
        ("purchasing", "purchased"),
        ("purchasing", "rejected"),
        ("purchasing", "unknown"),
        ("purchasing", "stopped"),
        ("purchasing", "watching"),
        ("purchased", "watching"),
        ("rejected", "watching"),
        ("unknown", "watching"),
        ("stopped", "watching"),
    }
    for current in STATES:
        for target in STATES:
            if (current, target) not in allowed:
                assert not can_transition(current, target), (current, target)


def test_a_finished_favorite_can_only_go_back_to_watching() -> None:
    for finished in ("purchased", "rejected", "unknown", "stopped"):
        targets = [s for s in STATES if can_transition(finished, s)]
        assert targets == ["watching"]


def test_models_are_immutable_and_hold_no_password() -> None:
    favorite = Favorite(
        id="f1",
        account_id="a1",
        product_id=807736,
        product_name="SD/豆本",
        payment_method="8",
        price_cap_yen=None,
        state="watching",
        state_version=0,
        state_changed_at=NOW,
    )
    account = Account(id="a1", label="テスト用 A", email="a@example.test")
    note = Notification(
        id="n1",
        favorite_id="f1",
        kind="purchased",
        message="ok",
        created_at=NOW,
        read=False,
    )

    for model, field in ((favorite, "state"), (account, "label"), (note, "read")):
        with pytest.raises(ValidationError):
            setattr(model, field, "x")
    assert "password" not in Account.model_fields
