from datetime import datetime, timedelta, timezone
import asyncio
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.auth.config import AuthSettings
from app.auth.models import TokenPair, UserCredential
from app.auth.repository import AuthRepository


class InvalidCredentialsError(PermissionError):
    """用户名、密码或用户状态不允许登录。"""


class InvalidAuthTokenError(PermissionError):
    """JWT 无效、过期、类型错误或已被撤销。"""


class PasswordPolicyError(ValueError):
    """新密码不符合当前密码策略。"""


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        settings: AuthSettings,
    ):
        self.repository = repository
        self.settings = settings
        self.password_hash = PasswordHash.recommended()
        self._dummy_hash = self.password_hash.hash(uuid4().hex)

    @staticmethod
    def _normalize_user_id(user_id: str) -> str:
        normalized = user_id.strip()
        if not normalized or len(normalized) > 64:
            raise InvalidCredentialsError("用户名或密码错误")
        return normalized

    @staticmethod
    def _normalize_password(password: str) -> str:
        if not password or len(password) > 256:
            raise InvalidCredentialsError("用户名或密码错误")
        return password

    def _verify_password(
        self,
        password: str,
        credential: UserCredential | None,
    ) -> tuple[bool, str | None]:
        stored_hash = (
            credential.password_hash
            if credential is not None
            else self._dummy_hash
        )
        try:
            return self.password_hash.verify_and_update(password, stored_hash)
        except Exception:
            return False, None

    async def authenticate_credentials(
        self,
        user_id: str,
        password: str,
    ) -> TokenPair:
        normalized_user_id = self._normalize_user_id(user_id)
        normalized_password = self._normalize_password(password)
        credential = await self.repository.get_credential(normalized_user_id)
        verified, updated_hash = await asyncio.to_thread(
            self._verify_password,
            normalized_password,
            credential,
        )
        if credential is None or not credential.is_active or not verified:
            raise InvalidCredentialsError("用户名或密码错误")
        if updated_hash is not None:
            await self.repository.update_password_hash(
                credential.user_id,
                credential.password_hash,
                updated_hash,
            )
        return await self._issue_new_pair(credential.user_id)

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        normalized_user_id = self._normalize_user_id(user_id)
        normalized_current = self._normalize_password(current_password)
        if not 12 <= len(new_password) <= 128:
            raise PasswordPolicyError("新密码长度必须为 12 到 128 个字符")

        credential = await self.repository.get_credential(normalized_user_id)
        verified, _ = await asyncio.to_thread(
            self._verify_password,
            normalized_current,
            credential,
        )
        if credential is None or not credential.is_active or not verified:
            raise InvalidCredentialsError("当前密码错误")
        if await asyncio.to_thread(
            self.password_hash.verify,
            new_password,
            credential.password_hash,
        ):
            raise PasswordPolicyError("新密码不能与当前密码相同")

        new_hash = await asyncio.to_thread(self.password_hash.hash, new_password)
        replaced = await self.repository.replace_password_and_revoke_sessions(
            credential.user_id,
            credential.password_hash,
            new_hash,
        )
        if not replaced:
            raise InvalidCredentialsError("密码已被其他请求修改，请重新登录")

    def _encode_token(
        self,
        *,
        user_id: str,
        token_id: str,
        token_type: str,
        expires_at: datetime,
        issued_at: datetime,
    ) -> str:
        return jwt.encode(
            {
                "sub": user_id,
                "jti": token_id,
                "type": token_type,
                "iat": issued_at,
                "exp": expires_at,
                "iss": self.settings.issuer,
                "aud": self.settings.audience,
            },
            self.settings.secret,
            algorithm=self.settings.algorithm,
        )

    def _build_pair(self, user_id: str) -> tuple[TokenPair, str, datetime]:
        issued_at = datetime.now(timezone.utc)
        access_expires_at = issued_at + timedelta(
            seconds=self.settings.access_token_seconds
        )
        refresh_expires_at = issued_at + timedelta(
            seconds=self.settings.refresh_token_seconds
        )
        access_token_id = uuid4().hex
        refresh_token_id = uuid4().hex
        pair = TokenPair(
            access_token=self._encode_token(
                user_id=user_id,
                token_id=access_token_id,
                token_type="access",
                expires_at=access_expires_at,
                issued_at=issued_at,
            ),
            refresh_token=self._encode_token(
                user_id=user_id,
                token_id=refresh_token_id,
                token_type="refresh",
                expires_at=refresh_expires_at,
                issued_at=issued_at,
            ),
            access_expires_in=self.settings.access_token_seconds,
            refresh_expires_in=self.settings.refresh_token_seconds,
        )
        return pair, refresh_token_id, refresh_expires_at.replace(tzinfo=None)

    async def _issue_new_pair(self, user_id: str) -> TokenPair:
        pair, refresh_token_id, refresh_expires_at = self._build_pair(user_id)
        await self.repository.create_refresh_session(
            refresh_token_id,
            user_id,
            refresh_expires_at,
        )
        return pair

    def _decode_token(self, token: str, expected_type: str) -> dict:
        try:
            claims = jwt.decode(
                token,
                self.settings.secret,
                algorithms=[self.settings.algorithm],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={
                    "require": ["sub", "jti", "type", "iat", "exp", "iss", "aud"]
                },
            )
        except InvalidTokenError as exc:
            raise InvalidAuthTokenError("登录凭证无效或已过期") from exc

        if claims.get("type") != expected_type:
            raise InvalidAuthTokenError("登录凭证类型错误")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise InvalidAuthTokenError("登录凭证缺少用户标识")
        if not isinstance(claims.get("jti"), str) or not claims["jti"]:
            raise InvalidAuthTokenError("登录凭证缺少令牌标识")
        return claims

    async def authenticate_access_token(self, token: str) -> str:
        claims = self._decode_token(token, "access")
        user_id = str(claims["sub"])
        credential = await self.repository.get_credential(user_id)
        if credential is None or not credential.is_active:
            raise InvalidAuthTokenError("登录凭证无效或用户已停用")
        return user_id

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._decode_token(refresh_token, "refresh")
        user_id = str(claims["sub"])
        credential = await self.repository.get_credential(user_id)
        if credential is None or not credential.is_active:
            raise InvalidAuthTokenError("登录凭证无效或用户已停用")

        pair, new_token_id, new_expires_at = self._build_pair(user_id)
        rotated = await self.repository.rotate_refresh_session(
            str(claims["jti"]),
            new_token_id,
            user_id,
            new_expires_at,
        )
        if not rotated:
            raise InvalidAuthTokenError("刷新令牌已失效或已被使用")
        return pair

    async def logout(self, refresh_token: str) -> None:
        claims = self._decode_token(refresh_token, "refresh")
        revoked = await self.repository.revoke_refresh_session(
            str(claims["jti"]),
            str(claims["sub"]),
        )
        if not revoked:
            raise InvalidAuthTokenError("刷新令牌已失效或已被使用")
