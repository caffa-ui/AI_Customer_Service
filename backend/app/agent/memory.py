from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from app.agent.State.state import SCRMState
from app.utils.config_handler import agent_config


_memory_config = agent_config.get("memory", {})

MIN_TOKENS_TO_COMPRESS = int(_memory_config.get("min_tokens_to_compress", 3000))
KEEP_TURNS = int(_memory_config.get("keep_turns", 10))
MAX_SUMMARY_CHARS = int(_memory_config.get("max_summary_chars", 1200))
RECENT_CONTEXT_MESSAGES = int(_memory_config.get("recent_context_messages", 20))
SUPERVISOR_CONTEXT_MESSAGES = int(
    _memory_config.get("supervisor_context_messages", 6)
)

EMPTY_MEMORY_SUMMARY = "暂无更早的会话记忆"


def get_memory_summary(state: SCRMState) -> str:
    """获取可直接插入 Prompt 的长期记忆。"""
    summary = (state.get("summary") or "").strip()
    return summary or EMPTY_MEMORY_SUMMARY


def get_recent_messages(
    state: SCRMState,
    limit: int = RECENT_CONTEXT_MESSAGES,
) -> list[BaseMessage]:
    """返回最近的短期会话上下文。"""
    messages = state.get("messages", [])
    return list(messages[-limit:]) if limit > 0 else []


def messages_to_context(
    messages: Sequence[BaseMessage],
    limit: int = SUPERVISOR_CONTEXT_MESSAGES,
) -> str:
    """将最近消息转为供分类节点参考的简短文本。"""
    selected = list(messages[-limit:]) if limit > 0 else []
    lines: list[str] = []
    for message in selected:
        content = message.content
        if isinstance(content, str):
            text = content.strip()
        else:
            text = str(content)
        if not text:
            continue
        # 分类只需要近期线索，避免单条消息无限膨胀。
        lines.append(f"{message.type}: {text[:500]}")
    return "\n".join(lines) or "暂无近期上下文"
