from cryptography.fernet import Fernet, InvalidToken

from spider.application.ports import SecretBoxError


def generate_key() -> str:
    return Fernet.generate_key().decode()


class FernetSecretBox:
    """資格情報の暗号化（Fernet）。鍵は環境変数で渡す（AWS では KMS に差し替える想定）。"""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())  # 不正な鍵は ValueError

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            raise SecretBoxError from None
