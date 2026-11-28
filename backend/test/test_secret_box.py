import pytest
from cryptography.fernet import Fernet

from spider.application.ports import SecretBoxError
from spider.infrastructure.secret_box import FernetSecretBox


def _key() -> str:
    return Fernet.generate_key().decode()


def test_encrypts_and_decrypts() -> None:
    box = FernetSecretBox(_key())

    token = box.encrypt("secret-pw")

    assert "secret-pw" not in token
    assert box.decrypt(token) == "secret-pw"


def test_the_same_value_encrypts_differently_each_time() -> None:
    box = FernetSecretBox(_key())

    assert box.encrypt("secret-pw") != box.encrypt("secret-pw")


def test_a_different_key_cannot_decrypt() -> None:
    token = FernetSecretBox(_key()).encrypt("secret-pw")

    with pytest.raises(SecretBoxError):
        FernetSecretBox(_key()).decrypt(token)


def test_garbage_cannot_be_decrypted() -> None:
    with pytest.raises(SecretBoxError):
        FernetSecretBox(_key()).decrypt("not-a-token")


def test_an_invalid_key_fails_at_startup() -> None:
    with pytest.raises(ValueError):
        FernetSecretBox("too-short")
