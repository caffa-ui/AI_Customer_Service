from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import (
    AuthServiceDependency,
    CurrentUserDependency,
    LoginLimiterDependency,
    unauthorized,
)
from app.api.schemas import (
    CurrentUserResponse,
    LogoutResponse,
    PasswordChangedResponse,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.auth.models import TokenPair
from app.auth.service import (
    InvalidAuthTokenError,
    InvalidCredentialsError,
    PasswordPolicyError,
)
from app.utils.logger_handler import get_logger


logger = get_logger("api_routes")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post("/token", response_model=TokenResponse)
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
        raise unauthorized("用户名或密码错误") from exc
    except Exception as exc:
        logger.error("登录接口执行失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    await rate_limiter.reset(rate_key)
    return _token_response(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> TokenResponse:
    try:
        pair = await auth_service.refresh(payload.refresh_token)
    except InvalidAuthTokenError as exc:
        raise unauthorized("刷新令牌无效、过期或已被使用") from exc
    except Exception as exc:
        logger.error("刷新令牌失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    return _token_response(pair)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    payload: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> LogoutResponse:
    try:
        await auth_service.logout(payload.refresh_token)
    except InvalidAuthTokenError as exc:
        raise unauthorized("刷新令牌无效、过期或已被使用") from exc
    except Exception as exc:
        logger.error("退出登录失败: error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务暂时不可用，请稍后重试",
        ) from exc
    return LogoutResponse()


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(user_id: CurrentUserDependency) -> CurrentUserResponse:
    return CurrentUserResponse(user_id=user_id)


@router.post("/change-password", response_model=PasswordChangedResponse)
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
        raise unauthorized("当前密码错误或登录状态已变化") from exc
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return PasswordChangedResponse()
