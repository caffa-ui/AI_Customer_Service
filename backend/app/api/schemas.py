from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]
ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=8000),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: Identifier | None = None
    message: ChatMessage
    request_id: Identifier | None = None


class ChatResponseBody(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    conversation_id: str
    user_id: str
    content: str
    message_id: str | None


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_expires_in: int


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ]


class CurrentUserResponse(BaseModel):
    user_id: str


class LogoutResponse(BaseModel):
    status: Literal["logged_out"] = "logged_out"


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[
        str,
        StringConstraints(min_length=1, max_length=256),
    ]
    new_password: Annotated[
        str,
        StringConstraints(min_length=12, max_length=128),
    ]


class PasswordChangedResponse(BaseModel):
    status: Literal["password_changed"] = "password_changed"


class ConversationSummaryResponse(BaseModel):
    conversation_id: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationSummaryResponse]


class ConversationMessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    message_id: str | None = None


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ConversationMessageResponse]


class ConversationDeletedResponse(BaseModel):
    status: Literal["deleted"] = "deleted"
