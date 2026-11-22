from spider.application.ports import SiteClient
from spider.application.retry import PreviewRuntime, retrying


async def check_login(
    client: SiteClient,
    email: str,
    password: str,
    *,
    runtime: PreviewRuntime,
    deadline_seconds: float,
) -> None:
    """ログインできるかだけを確認する（一時的エラーはリトライ。セッションは残さない）。"""
    await retrying(
        lambda: client.login(email, password),
        runtime=runtime,
        deadline_at=runtime.now() + deadline_seconds,
    )
