from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.middleware import HTTPRequestMiddleware
from app.api.rate_limit import LoginRateLimiter
from app.api.routes import router


AppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def _positive_int_env(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须是正整数")
    return value


def _cors_origins() -> list[str]:
    raw_value = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    )
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 延迟导入生产运行时，使 OpenAPI 生成和注入假服务的接口测试
    # 不必提前初始化模型、数据库与 RAG。
    from app.chat.runtime import create_runtime_services

    async with create_runtime_services() as services:
        app.state.chat_service = services.chat_service
        app.state.auth_service = services.auth_service
        try:
            yield
        finally:
            app.state.chat_service = None
            app.state.auth_service = None


def create_app(*, lifespan_context: AppLifespan = lifespan) -> FastAPI:
    application = FastAPI(
        title="SCRM AI 客服 API",
        version="0.1.0",
        lifespan=lifespan_context,
    )
    application.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=_positive_int_env("AUTH_LOGIN_MAX_ATTEMPTS", 5),
        window_seconds=_positive_int_env("AUTH_LOGIN_WINDOW_SECONDS", 300),
    )
    application.add_middleware(
        HTTPRequestMiddleware,
        timeout_seconds=_positive_int_env("API_REQUEST_TIMEOUT_SECONDS", 120),
        max_body_bytes=_positive_int_env("API_MAX_BODY_BYTES", 65536),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )
    application.include_router(router)
    application.mount(
        "/static",
        StaticFiles(directory=WEB_DIR / "static"),
        name="static",
    )

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unavailable")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "服务器内部错误",
                "request_id": request_id,
            },
        )

    return application


app = create_app()
