from collections.abc import Sequence
from langchain_core.messages import BaseMessage
from app.agent.State.state import SCRMState
from app.utils.config_handler import agent_config


_memory_config = agent_config.get("memory", {})

MIN_TOKENS_TO_COMPRESS = int(_memory_config.get("min_tokens_to_compress", 300000))
KEEP_TURNS = int(_memory_config.get("keep_turns", 10))
MAX_SUMMARY_CHARS = int(_memory_config.get("max_summary_chars", 12000))
RECENT_CONTEXT_MESSAGES = int(_memory_config.get("recent_context_messages", 20))
SUPERVISOR_CONTEXT_MESSAGES = int(
    _memory_config.get("supervisor_context_messages", 6)
)

EMPTY_MEMORY_SUMMARY = "暂无更早的会话记忆"


def get_memory_summary(state: SCRMState) -> str:
    summary = (state.get("summary") or "").strip()
    return summary or EMPTY_MEMORY_SUMMARY


def get_recent_messages(
    state: SCRMState,
    limit: int = RECENT_CONTEXT_MESSAGES,
) -> list[BaseMessage]:
    messages = state.get("messages", [])
    return list(messages[-limit:]) if limit > 0 else []


def messages_to_context(
    messages: Sequence[BaseMessage],
    limit: int = SUPERVISOR_CONTEXT_MESSAGES,
) -> str:
    """将最近几条消息转为供主管节点参考的简短文本。"""
    selected = list(messages[-limit:]) if limit > 0 else []
    lines: list[str] = []
    for message in selected:
        content = message.content
        if isinstance(content, str):
            text = content.strip()
        else:
            #将非文本类如图片转换成纯文本字符
            text = str(content)
        if not text:
            continue
        # 避免单条消息无限膨胀，主要防止如图片转换的纯文本造成token浪费，只要读取其文本前部分即可
        lines.append(f"{message.type}: {text[:500]}")
    return "\n".join(lines) or "暂无近期上下文"
