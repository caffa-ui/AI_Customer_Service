from datetime import datetime
from pathlib import Path
import sys
import unittest

from pwdlib import PasswordHash


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.config import AuthSettings
from app.auth.models import UserCredential
from app.auth.service import (
    AuthService,
    InvalidAuthTokenError,
    InvalidCredentialsError,
)


class FakeAuthRepository:
    def __init__(self, credentials: dict[str, UserCredential]):
        self.credentials = credentials
        self.sessions: dict[str, tuple[str, bool]] = {}

    async def verify_schema(self) -> None:
        return None

    async def get_credential(self, user_id: str) -> UserCredential | None:
        return self.credentials.get(user_id)

    async def update_password_hash(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> None:
        credential = self.credentials[user_id]
        if credential.password_hash == old_hash:
            self.credentials[user_id] = UserCredential(
                user_id=user_id,
                password_hash=new_hash,
                is_active=credential.is_active,
            )

    async def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        self.sessions[token_id] = (user_id, False)

    async def replace_password_and_revoke_sessions(
        self,
        user_id: str,
        old_hash: str,
        new_hash: str,
    ) -> bool:
        credential = self.credentials[user_id]
        if credential.password_hash != old_hash:
            return False
        self.credentials[user_id] = UserCredential(
            user_id=user_id,
            password_hash=new_hash,
            is_active=credential.is_active,
        )
        for token_id, (session_user_id, revoked) in list(self.sessions.items()):
            if session_user_id == user_id and not revoked:
                self.sessions[token_id] = (session_user_id, True)
        return True

    async def rotate_refresh_session(
        self,
        current_token_id: str,
        new_token_id: str,
        user_id: str,
        new_expires_at: datetime,
    ) -> bool:
        session = self.sessions.get(current_token_id)
        if session != (user_id, False):
            return False
        self.sessions[current_token_id] = (user_id, True)
        self.sessions[new_token_id] = (user_id, False)
        return True

    async def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        session = self.sessions.get(token_id)
        if session != (user_id, False):
            return False
        self.sessions[token_id] = (user_id, True)
        return True


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.correct_password = "CorrectPassword@2026"
        cls.password_hash = PasswordHash.recommended().hash(
            cls.correct_password
        )

    def setUp(self):
        self.repository = FakeAuthRepository(
            {
                "active-user": UserCredential(
                    user_id="active-user",
                    password_hash=self.password_hash,
                    is_active=True,
                ),
                "inactive-user": UserCredential(
                    user_id="inactive-user",
                    password_hash=self.password_hash,
                    is_active=False,
                ),
            }
        )
        self.service = AuthService(
            self.repository,
            AuthSettings(
                secret="a" * 64,
                issuer="test-issuer",
                audience="test-audience",
                access_token_seconds=1800,
                refresh_token_seconds=604800,
            ),
        )

    async def test_login_issues_access_and_refresh_tokens(self):
        pair = await self.service.authenticate_credentials(
            "active-user",
            self.correct_password,
        )

        user_id = await self.service.authenticate_access_token(
            pair.access_token
        )
        self.assertEqual(user_id, "active-user")
        self.assertEqual(pair.access_expires_in, 1800)
        self.assertEqual(len(self.repository.sessions), 1)

    async def test_login_hides_unknown_password_and_inactive_user(self):
        attempts = (
            ("unknown-user", self.correct_password),
            ("active-user", "wrong-password"),
            ("inactive-user", self.correct_password),
        )
        for user_id, password in attempts:
            with self.subTest(user_id=user_id):
                with self.assertRaises(InvalidCredentialsError):
                    await self.service.authenticate_credentials(
                        user_id,
                        password,
                    )

    async def test_refresh_token_is_rotated_and_cannot_be_replayed(self):
        original = await self.service.authenticate_credentials(
            "active-user",
            self.correct_password,
        )
        replacement = await self.service.refresh(original.refresh_token)

        self.assertEqual(
            await self.service.authenticate_access_token(
                replacement.access_token
            ),
            "active-user",
        )
        with self.assertRaises(InvalidAuthTokenError):
            await self.service.refresh(original.refresh_token)

    async def test_logout_revokes_refresh_token(self):
        pair = await self.service.authenticate_credentials(
            "active-user",
            self.correct_password,
        )
        await self.service.logout(pair.refresh_token)

        with self.assertRaises(InvalidAuthTokenError):
            await self.service.logout(pair.refresh_token)

    async def test_refresh_token_cannot_be_used_as_access_token(self):
        pair = await self.service.authenticate_credentials(
            "active-user",
            self.correct_password,
        )
        with self.assertRaises(InvalidAuthTokenError):
            await self.service.authenticate_access_token(pair.refresh_token)

    async def test_change_password_revokes_refresh_sessions(self):
        pair = await self.service.authenticate_credentials(
            "active-user",
            self.correct_password,
        )
        new_password = "NewCorrectPassword@2026"
        await self.service.change_password(
            "active-user",
            self.correct_password,
            new_password,
        )

        with self.assertRaises(InvalidAuthTokenError):
            await self.service.refresh(pair.refresh_token)
        with self.assertRaises(InvalidCredentialsError):
            await self.service.authenticate_credentials(
                "active-user",
                self.correct_password,
            )
        replacement = await self.service.authenticate_credentials(
            "active-user",
            new_password,
        )
        self.assertTrue(replacement.access_token)


if __name__ == "__main__":
    unittest.main()
