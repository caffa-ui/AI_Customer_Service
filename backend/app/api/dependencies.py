import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.api.rate_limit import LoginRateLimiter
from app.auth.service import AuthService, InvalidAuthTokenError
from app.chat.service import ChatService
from app.ticket.service import TicketService


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


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


def get_ticket_service(request: Request) -> TicketService:
    service = getattr(request.app.state, "ticket_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="退款服务尚未就绪")
    return service


ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
LoginLimiterDependency = Annotated[
    LoginRateLimiter,
    Depends(get_login_rate_limiter),
]
TicketServiceDependency = Annotated[TicketService, Depends(get_ticket_service)]


def unauthorized(detail: str = "登录凭证无效或已过期") -> HTTPException:
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
        raise unauthorized() from exc


CurrentUserDependency = Annotated[str, Depends(get_current_user_id)]


def require_admin(user_id: CurrentUserDependency) -> str:
    admins = {
        item.strip()
        for item in os.getenv("ADMIN_USER_IDS", "admin").split(",")
        if item.strip()
    }
    if user_id not in admins:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user_id


AdminUserDependency = Annotated[str, Depends(require_admin)]
