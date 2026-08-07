from dataclasses import dataclass
import os
from pathlib import Path
import secrets


DEFAULT_SECRET_PATH = Path(__file__).resolve().parents[2] / ".jwt_secret"


def _positive_int_env(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须是正整数")
    return value


def _valid_secret(secret: str) -> str:
    normalized = secret.strip()
    if len(normalized) < 32 or normalized.startswith("replace_with_"):
        raise RuntimeError(
            "JWT_SECRET 必须替换为至少 32 个字符的随机值"
        )
    return normalized


def _load_or_create_secret() -> str:
    configured = os.getenv("JWT_SECRET")
    if configured is not None:
        return _valid_secret(configured)

    try:
        return _valid_secret(DEFAULT_SECRET_PATH.read_text(encoding="ascii"))
    except FileNotFoundError:
        generated = secrets.token_hex(32)
        try:
            descriptor = os.open(
                DEFAULT_SECRET_PATH,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            return _valid_secret(
                DEFAULT_SECRET_PATH.read_text(encoding="ascii")
            )
        with os.fdopen(descriptor, "w", encoding="ascii") as secret_file:
            secret_file.write(generated)
        return generated


@dataclass(frozen=True, slots=True)
class AuthSettings:
    secret: str
    issuer: str
    audience: str
    access_token_seconds: int
    refresh_token_seconds: int
    algorithm: str = "HS256"

    @classmethod
    def from_env(cls) -> "AuthSettings":
        issuer = (os.getenv("JWT_ISSUER") or "scrm-agent").strip()
        audience = (os.getenv("JWT_AUDIENCE") or "scrm-api").strip()
        if not issuer:
            raise RuntimeError("JWT_ISSUER 不能为空")
        if not audience:
            raise RuntimeError("JWT_AUDIENCE 不能为空")

        access_minutes = _positive_int_env(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
            30,
        )
        refresh_days = _positive_int_env("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7)
        return cls(
            secret=_load_or_create_secret(),
            issuer=issuer,
            audience=audience,
            access_token_seconds=access_minutes * 60,
            refresh_token_seconds=refresh_days * 24 * 60 * 60,
        )
