import pytest
from cryptography.fernet import Fernet

from spider.wiring import build_store


def test_a_missing_credentials_key_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="CREDENTIALS_KEY"):
        build_store({})


def test_an_invalid_credentials_key_fails_at_startup() -> None:
    with pytest.raises(ValueError):
        build_store({"CREDENTIALS_KEY": "too-short"})


def test_the_store_is_built_from_the_environment() -> None:
    store, _ = build_store(
        {
            "CREDENTIALS_KEY": Fernet.generate_key().decode(),
            "DYNAMODB_ENDPOINT": "http://localhost:8001",
            "TABLE_PREFIX": "t-",
        }
    )

    assert store.secret_box.decrypt(store.secret_box.encrypt("x")) == "x"
