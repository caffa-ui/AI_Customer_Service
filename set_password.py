import argparse
import asyncio
from getpass import getpass
from pathlib import Path
import selectors
import sys

from dotenv import load_dotenv
from pwdlib import PasswordHash
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.mysql import create_mysql_engine, verify_mysql_connection


def _read_new_password() -> str:
    password = getpass("请输入新密码: ")
    confirmation = getpass("请再次输入新密码: ")
    if password != confirmation:
        raise RuntimeError("两次输入的密码不一致")
    if not 12 <= len(password) <= 128:
        raise RuntimeError("密码长度必须为 12 到 128 个字符")
    return password


async def set_password(user_id: str, password: str) -> None:
    engine = create_mysql_engine()
    try:
        await verify_mysql_connection(engine)
        password_hash = await asyncio.to_thread(
            PasswordHash.recommended().hash,
            password,
        )
        async with engine.begin() as connection:
            result = await connection.execute(
                text("SELECT 1 FROM users WHERE user_id = :user_id LIMIT 1"),
                {"user_id": user_id},
            )
            if result.first() is None:
                raise RuntimeError("用户不存在，不能设置登录密码")

            await connection.execute(
                text(
                    """
                    INSERT INTO user_credentials (user_id, password_hash)
                    VALUES (:user_id, :password_hash)
                    ON DUPLICATE KEY UPDATE
                        password_hash = VALUES(password_hash),
                        password_changed_at = UTC_TIMESTAMP(6)
                    """
                ),
                {"user_id": user_id, "password_hash": password_hash},
            )
            await connection.execute(
                text(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = UTC_TIMESTAMP(6)
                    WHERE user_id = :user_id AND revoked_at IS NULL
                    """
                ),
                {"user_id": user_id},
            )
    finally:
        await engine.dispose()


async def run() -> None:
    parser = argparse.ArgumentParser(
        description="设置 MySQL 用户登录密码并撤销其现有刷新令牌",
    )
    parser.add_argument("user_id", help="users 表中的 user_id")
    args = parser.parse_args()
    user_id = args.user_id.strip()
    if not user_id or len(user_id) > 64:
        raise RuntimeError("user_id 格式无效")
    await set_password(user_id, _read_new_password())
    print(f"用户 {user_id} 的密码已更新，已有刷新令牌已撤销。")


if __name__ == "__main__":
    load_dotenv(BACKEND_DIR / ".env", override=False)
    try:
        if sys.platform == "win32":
            with asyncio.Runner(
                loop_factory=lambda: asyncio.SelectorEventLoop(
                    selectors.SelectSelector()
                )
            ) as runner:
                runner.run(run())
        else:
            asyncio.run(run())
    except RuntimeError as exc:
        print(f"设置密码失败: {exc}")
        raise SystemExit(1) from exc
