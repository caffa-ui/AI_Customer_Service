from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import create_app
from app.auth.models import TokenPair
from app.auth.service import InvalidAuthTokenError, InvalidCredentialsError
from app.chat.service import ChatResponse
from app.conversation.models import Conversation
from app.conversation.repository import ConversationAccessError
from app.user.repository import UserAccessError


class FakeChatService:
    def __init__(self):
        self.calls: list[dict] = []
        self.error: Exception | None = None
        now = datetime.now(timezone.utc)
        self.conversations = {
            "conversation-001": Conversation(
                conversation_id="conversation-001",
                user_id="cli-user",
                created_at=now,
                updated_at=now,
            )
        }

    async def chat(self, **kwargs) -> ChatResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return ChatResponse(
            request_id=kwargs["request_id"] or "generated-request",
            conversation_id=kwargs["conversation_id"],
            user_id=kwargs["user_id"],
            content="这是测试回答",
            message_id="message-1",
        )

    async def list_conversations(self, **kwargs) -> list[Conversation]:
        return list(self.conversations.values())

    async def get_state(self, **kwargs) -> dict:
        from langchain_core.messages import AIMessage, HumanMessage

        return {
            "messages": [
                HumanMessage(content="历史问题", id="history-user"),
                AIMessage(content="历史回答", id="history-ai"),
            ]
        }

    async def delete_conversation(self, **kwargs) -> bool:
        return self.conversations.pop(kwargs["conversation_id"], None) is not None


class FakeAuthService:
    def __init__(self):
        self.access_tokens = {"access-1": "cli-user"}
        self.refresh_tokens = {"refresh-1": "cli-user"}
        self.password = "correct-password"

    @staticmethod
    def _pair(suffix: str) -> TokenPair:
        return TokenPair(
            access_token=f"access-{suffix}",
            refresh_token=f"refresh-{suffix}",
            access_expires_in=1800,
            refresh_expires_in=604800,
        )

    async def authenticate_credentials(
        self,
        user_id: str,
        password: str,
    ) -> TokenPair:
        if user_id != "cli-user" or password != self.password:
            raise InvalidCredentialsError("用户名或密码错误")
        return self._pair("1")

    async def authenticate_access_token(self, token: str) -> str:
        user_id = self.access_tokens.get(token)
        if user_id is None:
            raise InvalidAuthTokenError("登录凭证无效")
        return user_id

    async def refresh(self, refresh_token: str) -> TokenPair:
        user_id = self.refresh_tokens.pop(refresh_token, None)
        if user_id is None:
            raise InvalidAuthTokenError("刷新令牌无效")
        pair = self._pair("2")
        self.access_tokens[pair.access_token] = user_id
        self.refresh_tokens[pair.refresh_token] = user_id
        return pair

    async def logout(self, refresh_token: str) -> None:
        if self.refresh_tokens.pop(refresh_token, None) is None:
            raise InvalidAuthTokenError("刷新令牌无效")

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        if user_id != "cli-user" or current_password != self.password:
            raise InvalidCredentialsError("当前密码错误")
        self.password = new_password
        self.refresh_tokens.clear()


class FastAPITests(unittest.TestCase):
    def setUp(self):
        self.chat_service = FakeChatService()
        self.auth_service = FakeAuthService()

        @asynccontextmanager
        async def fake_lifespan(app: FastAPI):
            app.state.chat_service = self.chat_service
            app.state.auth_service = self.auth_service
            try:
                yield
            finally:
                app.state.chat_service = None
                app.state.auth_service = None

        self.app = create_app(lifespan_context=fake_lifespan)

    def test_health_and_ready(self):
        with TestClient(self.app) as client:
            health = client.get("/health", headers={"X-Request-ID": "test-health"})
            self.assertEqual(health.json(), {"status": "ok"})
            self.assertEqual(health.headers["X-Request-ID"], "test-health")
            self.assertIn("X-Process-Time-Ms", health.headers)
            self.assertEqual(client.get("/ready").json(), {"status": "ready"})

    def test_chat_generates_conversation_id(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/v1/chat",
                json={"message": " 你好 "},
                headers={"Authorization": "Bearer access-1"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], "cli-user")
        self.assertEqual(body["content"], "这是测试回答")
        self.assertEqual(len(body["conversation_id"]), 32)
        self.assertEqual(self.chat_service.calls[0]["message"], "你好")

    def test_chat_preserves_client_identifiers(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/v1/chat",
                json={
                    "conversation_id": "conversation-001",
                    "request_id": "request-001",
                    "message": "查询我的工单",
                },
                headers={"Authorization": "Bearer access-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], "request-001")
        self.assertEqual(
            self.chat_service.calls[0]["conversation_id"],
            "conversation-001",
        )

    def test_access_errors_do_not_expose_account_state(self):
        for error in (
            UserAccessError("用户不存在"),
            ConversationAccessError("会话不属于当前用户"),
        ):
            with self.subTest(error=type(error).__name__):
                self.chat_service.error = error
                with TestClient(self.app) as client:
                    response = client.post(
                        "/api/v1/chat",
                        json={"message": "你好"},
                        headers={"Authorization": "Bearer access-1"},
                    )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["detail"],
                    "当前用户无权访问该会话",
                )

    def test_request_validation(self):
        invalid_payloads = (
            {"message": "   "},
            {"message": "你好", "conversation_id": "bad/id"},
            {"message": "你好", "user_id": "cannot-be-trusted"},
            {"message": "你好", "unknown": True},
        )
        with TestClient(self.app) as client:
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    response = client.post(
                        "/api/v1/chat",
                        json=payload,
                        headers={"Authorization": "Bearer access-1"},
                    )
                    self.assertEqual(response.status_code, 422)

        self.assertEqual(self.chat_service.calls, [])

    def test_unready_application_returns_503(self):
        @asynccontextmanager
        async def unready_lifespan(app: FastAPI):
            app.state.chat_service = None
            app.state.auth_service = None
            yield

        app = create_app(lifespan_context=unready_lifespan)
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/ready").status_code, 503)
            response = client.post(
                "/api/v1/chat",
                json={"message": "你好"},
                headers={"Authorization": "Bearer access-1"},
            )
            self.assertEqual(response.status_code, 503)

    def test_login_and_current_user(self):
        with TestClient(self.app) as client:
            token_response = client.post(
                "/api/v1/auth/token",
                data={"username": "cli-user", "password": "correct-password"},
            )
            me_response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer access-1"},
            )

        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(token_response.json()["access_token"], "access-1")
        self.assertEqual(token_response.json()["token_type"], "bearer")
        self.assertEqual(me_response.json(), {"user_id": "cli-user"})

    def test_invalid_login_and_access_token_return_401(self):
        with TestClient(self.app) as client:
            login_response = client.post(
                "/api/v1/auth/token",
                data={"username": "cli-user", "password": "wrong"},
            )
            missing_response = client.get("/api/v1/auth/me")
            invalid_response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid"},
            )

        self.assertEqual(login_response.status_code, 401)
        self.assertEqual(missing_response.status_code, 401)
        self.assertEqual(invalid_response.status_code, 401)

    def test_refresh_rotates_token_and_logout_revokes_it(self):
        with TestClient(self.app) as client:
            refresh_response = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "refresh-1"},
            )
            replay_response = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "refresh-1"},
            )
            logout_response = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": "refresh-2"},
            )
            second_logout = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": "refresh-2"},
            )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(refresh_response.json()["access_token"], "access-2")
        self.assertEqual(replay_response.status_code, 401)
        self.assertEqual(logout_response.json(), {"status": "logged_out"})
        self.assertEqual(second_logout.status_code, 401)

    def test_web_page_and_static_assets(self):
        with TestClient(self.app) as client:
            page = client.get("/")
            script = client.get("/static/app.js")
            favicon = client.get("/favicon.ico")

        self.assertEqual(page.status_code, 200)
        self.assertIn("SCRM AI 客服", page.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("refreshSession", script.text)
        self.assertEqual(favicon.status_code, 200)

    def test_login_is_rate_limited_after_repeated_failures(self):
        with TestClient(self.app) as client:
            responses = [
                client.post(
                    "/api/v1/auth/token",
                    data={"username": "cli-user", "password": "wrong"},
                )
                for _ in range(6)
            ]

        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)
        self.assertIn("Retry-After", responses[5].headers)

    def test_change_password_uses_authenticated_user(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/v1/auth/change-password",
                json={
                    "current_password": "correct-password",
                    "new_password": "new-password-2026",
                },
                headers={"Authorization": "Bearer access-1"},
            )

        self.assertEqual(response.json(), {"status": "password_changed"})
        self.assertEqual(self.auth_service.password, "new-password-2026")

    def test_conversation_list_history_and_delete(self):
        headers = {"Authorization": "Bearer access-1"}
        with TestClient(self.app) as client:
            listing = client.get("/api/v1/conversations", headers=headers)
            history = client.get(
                "/api/v1/conversations/conversation-001",
                headers=headers,
            )
            deleted = client.delete(
                "/api/v1/conversations/conversation-001",
                headers=headers,
            )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["conversation_id"], "conversation-001")
        self.assertEqual([item["role"] for item in history.json()["messages"]], ["user", "assistant"])
        self.assertEqual(deleted.json(), {"status": "deleted"})

    def test_request_body_limit(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/v1/chat",
                content="x" * 70000,
                headers={
                    "Authorization": "Bearer access-1",
                    "Content-Type": "application/json",
                },
            )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
