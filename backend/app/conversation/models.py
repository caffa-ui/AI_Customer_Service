from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Conversation:
    """一条用户会话的归属信息。"""

    conversation_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
