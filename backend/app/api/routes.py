import logging
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path as APIPath, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.api.schemas import (
    ChatRequest,
    ChatResponseBody,
    CurrentUserResponse,
    ConversationDeletedResponse,
    ConversationHistoryResponse,
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    HealthResponse,
    LogoutResponse,
    PasswordChangedResponse,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.auth.models import TokenPair
from app.auth.service import (
    AuthService,
    InvalidAuthTokenError,
    InvalidCredentialsError,
    PasswordPolicyError,
)
from app.api.rate_limit import LoginRateLimiter
from app.chat.service import ChatService
from app.conversation.repository import (
    ConversationAccessError,
    ConversationNotFoundError,
)
from app.user.repository import UserAccessError


logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def get_chat_service(request: Request) -> ChatService:
    chat_service = getattr(request.app.state, "chat_service", None)
    if chat_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能体服务尚未就绪",
        )
    return chat_service


def get_auth_service(request: Request) -> AuthService:
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务尚未就绪",
        )
    return auth_service


def get_login_rate_limiter(request: Request) -> LoginRateLimiter:
    return request.app.state.login_rate_limiter


ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
LoginLimiterDependency = Annotated[
    LoginRateLimiter,
    Depends(get_login_rate_limiter),
]


def _unauthorized(detail: str = "登录凭证无效或已过期") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: AuthServiceDependency,
) -> str:
    try:
        return await auth_service.authenticate_access_token(token)
    except InvalidAuthTokenError as exc:
        raise _unauthorized() from exc


CurrentUserDependency = Annotated[str, Depends(get_current_user_id)]


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.get("/", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(WEB_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, tags=["system"])
async def ready(request: Request) -> HealthResponse:
    if (
        getattr(request.app.state, "chat_service", None) is None
        or getattr(request.app.state, "auth_service", None) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能体服务尚未就绪",
        )
    return HealthResponse(status="ready")


@router.post(
    "/api/v1/auth/token",
    response_model=TokenResponse,
    tags=["auth"],
)
async def issue_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthServiceDependency,
    rate_limiter: LoginLimiterDependency,
) -> TokenResponse:
    client_host = request.client.host if request.client is not None else "unknown"
    rate_key = f"{client_host}:{form_data.username.strip().lower()}"
    retry_after = await rate_limiter.retry_after(rate_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        pair = await auth_service.authenticate_credentials(
            form_data.username,
            form_data.password,
        )
    except InvalidCredentialsError as exc:
        await rate_limiter.record_failure(rate_key)
        raise _unauthorized("用户名或密码错误") from exc
    except Exception as exc:
        logger.error("登录接口执行失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    await rate_limiter.reset(rate_key)
    return _token_response(pair)


@router.post(
    "/api/v1/auth/refresh",
    response_model=TokenResponse,
    tags=["auth"],
)
async def refresh_token(
    payload: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> TokenResponse:
    try:
        pair = await auth_service.refresh(payload.refresh_token)
    except InvalidAuthTokenError as exc:
        raise _unauthorized("刷新令牌无效、过期或已被使用") from exc
    except Exception as exc:
        logger.error("刷新令牌失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    return _token_response(pair)


@router.post(
    "/api/v1/auth/logout",
    response_model=LogoutResponse,
    tags=["auth"],
)
async def logout(
    payload: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> LogoutResponse:
    try:
        await auth_service.logout(payload.refresh_token)
    except InvalidAuthTokenError as exc:
        raise _unauthorized("刷新令牌无效、过期或已被使用") from exc
    except Exception as exc:
        logger.error("退出登录失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    return LogoutResponse()


@router.get(
    "/api/v1/auth/me",
    response_model=CurrentUserResponse,
    tags=["auth"],
)
async def current_user(user_id: CurrentUserDependency) -> CurrentUserResponse:
    return CurrentUserResponse(user_id=user_id)


@router.post(
    "/api/v1/auth/change-password",
    response_model=PasswordChangedResponse,
    tags=["auth"],
)
async def change_password(
    payload: PasswordChangeRequest,
    user_id: CurrentUserDependency,
    auth_service: AuthServiceDependency,
) -> PasswordChangedResponse:
    try:
        await auth_service.change_password(
            user_id,
            payload.current_password,
            payload.new_password,
        )
    except InvalidCredentialsError as exc:
        raise _unauthorized("当前密码错误或登录状态已变化") from exc
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return PasswordChangedResponse()


@router.get(
    "/api/v1/conversations",
    response_model=ConversationListResponse,
    tags=["conversations"],
)
async def list_conversations(
    user_id: CurrentUserDependency,
    chat_service: ChatServiceDependency,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ConversationListResponse:
    conversations = await chat_service.list_conversations(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[
            ConversationSummaryResponse(
                conversation_id=item.conversation_id,
                created_at=item.created_at.isoformat(),
                updated_at=item.updated_at.isoformat(),
            )
            for item in conversations
        ]
    )


@router.get(
    "/api/v1/conversations/{conversation_id}",
    response_model=ConversationHistoryResponse,
    tags=["conversations"],
)
async def conversation_history(
    conversation_id: Annotated[
        str,
        APIPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    ],
    user_id: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ConversationHistoryResponse:
    try:
        state = await chat_service.get_state(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except ConversationAccessError as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话") from exc

    messages: list[ConversationMessageResponse] = []
    for message in state.get("messages", []):
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        if not content.strip():
            continue
        messages.append(
            ConversationMessageResponse(
                role=role,
                content=content,
                message_id=getattr(message, "id", None),
            )
        )
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=messages,
    )


@router.delete(
    "/api/v1/conversations/{conversation_id}",
    response_model=ConversationDeletedResponse,
    tags=["conversations"],
)
async def delete_conversation(
    conversation_id: Annotated[
        str,
        APIPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    ],
    user_id: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ConversationDeletedResponse:
    try:
        await chat_service.delete_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except ConversationAccessError as exc:
        raise HTTPException(status_code=403, detail="无权访问该会话") from exc
    return ConversationDeletedResponse()


@router.post(
    "/api/v1/chat",
    response_model=ChatResponseBody,
    tags=["chat"],
)
async def chat(
    request: Request,
    payload: ChatRequest,
    chat_service: ChatServiceDependency,
    user_id: CurrentUserDependency,
) -> ChatResponseBody:
    conversation_id = payload.conversation_id or uuid4().hex
    try:
        response = await chat_service.chat(
            user_id=user_id,
            conversation_id=conversation_id,
            message=payload.message,
            request_id=payload.request_id or request.state.request_id,
        )
    except (UserAccessError, ConversationAccessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户无权访问该会话",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "聊天接口执行失败: error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="智能体服务暂时不可用，请稍后重试",
        ) from exc

    return ChatResponseBody.model_validate(response)
