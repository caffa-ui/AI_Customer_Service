from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from hashlib import sha256
from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class RequestContext:
    """单次聊天请求的安全日志上下文。"""

    request_id: str
    user_ref: str
    conversation_ref: str


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "scrm_request_context",
    default=None,
)


def identifier_ref(value: str) -> str:
    """将用户/会话标识转换为不可逆短引用，避免原始 ID 进入日志。"""
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def create_request_context(
    *,
    request_id: str,
    user_id: str,
    conversation_id: str,
) -> RequestContext:
    return RequestContext(
        request_id=request_id,
        user_ref=identifier_ref(user_id),
        conversation_ref=identifier_ref(conversation_id),
    )


def get_request_context() -> RequestContext | None:
    return _request_context.get()


@contextmanager
def bind_request_context(context: RequestContext) -> Iterator[RequestContext]:
    """绑定当前异步任务的上下文，并在请求结束时可靠恢复。"""
    token: Token = _request_context.set(context)
    try:
        yield context
    finally:
        _request_context.reset(token)
