from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from app.api.dependencies import ChatServiceDependency, CurrentUserDependency
from app.api.schemas import ChatRequest, ChatResponseBody
from app.conversation.repository import ConversationAccessError
from app.user.repository import UserAccessError
from app.utils.logger_handler import get_logger


logger = get_logger("api_routes")
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponseBody)
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
