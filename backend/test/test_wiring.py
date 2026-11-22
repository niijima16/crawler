import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


# --- 鍵ファイル（ローカル専用。CREDENTIALS_KEY が無いとき） ---------------------------------


def _roundtrip(env: dict[str, str]) -> str:
    store, _ = build_store(env)
    return store.secret_box.encrypt("x")


def test_the_environment_variable_wins_over_the_key_file(tmp_path: Path) -> None:
    key_file = tmp_path / "credentials.key"
    key = Fernet.generate_key().decode()

    store, _ = build_store({"CREDENTIALS_KEY": key, "CREDENTIALS_KEY_FILE": str(key_file)})

    assert not key_file.exists()
    assert Fernet(key.encode()).decrypt(store.secret_box.encrypt("x").encode()) == b"x"


def test_an_empty_environment_variable_counts_as_unset(tmp_path: Path) -> None:
    key_file = tmp_path / "credentials.key"

    build_store({"CREDENTIALS_KEY": "", "CREDENTIALS_KEY_FILE": str(key_file)})

    assert key_file.exists()


def test_a_missing_key_file_is_created_with_a_valid_key_that_only_the_owner_can_read(
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "keys" / "credentials.key"

    build_store({"CREDENTIALS_KEY_FILE": str(key_file)})

    Fernet(key_file.read_text().strip().encode())  # 有効な鍵
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_the_same_key_is_reused_on_the_next_start(tmp_path: Path) -> None:
    env = {"CREDENTIALS_KEY_FILE": str(tmp_path / "credentials.key")}
    store, _ = build_store(env)
    token = store.secret_box.encrypt("secret-pw")

    again, _ = build_store(env)

    assert again.secret_box.decrypt(token) == "secret-pw"


def test_an_existing_key_file_is_used(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode()
    key_file = tmp_path / "credentials.key"
    key_file.write_text(key + "\n")

    store, _ = build_store({"CREDENTIALS_KEY_FILE": str(key_file)})

    assert Fernet(key.encode()).decrypt(store.secret_box.encrypt("x").encode()) == b"x"


def test_services_starting_at_the_same_time_end_up_with_the_same_key(tmp_path: Path) -> None:
    env = {"CREDENTIALS_KEY_FILE": str(tmp_path / "credentials.key")}

    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _: _roundtrip(env), range(8)))

    key = (tmp_path / "credentials.key").read_text().strip().encode()
    assert all(Fernet(key).decrypt(t.encode()) == b"x" for t in tokens)


def test_a_broken_key_file_fails_at_startup(tmp_path: Path) -> None:
    key_file = tmp_path / "credentials.key"
    key_file.write_text("not-a-key")

    with pytest.raises(ValueError):
        build_store({"CREDENTIALS_KEY_FILE": str(key_file)})


def test_neither_a_key_nor_a_key_file_still_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="CREDENTIALS_KEY"):
        build_store({"CREDENTIALS_KEY": ""})
