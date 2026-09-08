from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as APIPath, Query
from langchain_core.messages import AIMessage, HumanMessage

from app.api.dependencies import ChatServiceDependency, CurrentUserDependency
from app.api.schemas import (
    ConversationDeletedResponse,
    ConversationHistoryResponse,
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
)
from app.conversation.repository import (
    ConversationAccessError,
    ConversationNotFoundError,
)


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
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


@router.get("/{conversation_id}", response_model=ConversationHistoryResponse)
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


@router.delete("/{conversation_id}", response_model=ConversationDeletedResponse)
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
