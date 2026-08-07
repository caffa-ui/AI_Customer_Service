import json
import threading
from time import perf_counter
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.middleware.context import RequestContext
from app.utils.logger_handler import get_logger


logger = get_logger("agent_monitoring")


def _duration_ms(started_at: float | None) -> int | None:
    if started_at is None:
        return None
    return max(0, round((perf_counter() - started_at) * 1000))


def _model_name(
    serialized: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> str:
    metadata = metadata or {}
    candidates = (
        metadata.get("ls_model_name"),
        serialized.get("name"),
        (serialized.get("kwargs") or {}).get("model"),
        (serialized.get("kwargs") or {}).get("model_name"),
    )
    return next((str(value) for value in candidates if value), "unknown")


def _usage_from_message(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return {}

    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "prompt_token_count"),
        "output_tokens": (
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
        ),
        "total_tokens": ("total_tokens", "total_token_count"),
    }
    normalized: dict[str, int] = {}
    for target, source_names in aliases.items():
        value = next(
            (usage.get(name) for name in source_names if usage.get(name) is not None),
            None,
        )
        if isinstance(value, int):
            normalized[target] = value
    return normalized


def _extract_usage(response: LLMResult) -> dict[str, int]:
    for batch in response.generations:
        for generation in batch:
            usage = _usage_from_message(getattr(generation, "message", None))
            if usage:
                return usage

    llm_output = response.llm_output or {}
    raw_usage = (
        llm_output.get("token_usage")
        or llm_output.get("usage")
        or llm_output.get("usage_metadata")
        or {}
    )
    if not isinstance(raw_usage, dict):
        return {}

    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "prompt_token_count"),
        "output_tokens": (
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
        ),
        "total_tokens": ("total_tokens", "total_token_count"),
    }
    normalized: dict[str, int] = {}
    for target, source_names in aliases.items():
        value = next(
            (
                raw_usage.get(name)
                for name in source_names
                if raw_usage.get(name) is not None
            ),
            None,
        )
        if isinstance(value, int):
            normalized[target] = value
    return normalized


class AgentMonitoringCallback(BaseCallbackHandler):
    """监控模型和工具调用，不记录输入正文、参数值或输出正文。"""

    def __init__(self, context: RequestContext):
        self.context = context
        self._model_runs: dict[UUID, tuple[float, str]] = {}
        self._tool_runs: dict[UUID, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _base_fields(self) -> str:
        return (
            f"request_id={self.context.request_id} "
            f"user_ref={self.context.user_ref} "
            f"conversation_ref={self.context.conversation_ref}"
        )

    def _pop_run(
        self,
        storage: dict[UUID, tuple[float, str]],
        run_id: UUID,
    ) -> tuple[float | None, str]:
        with self._lock:
            return storage.pop(run_id, (None, "unknown"))

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model_name = _model_name(serialized, metadata)
        with self._lock:
            self._model_runs[run_id] = (perf_counter(), model_name)
        message_count = sum(len(batch) for batch in messages)
        logger.info(
            f"event=model_started {self._base_fields()} "
            f"model={model_name} "
            f"message_count={message_count}"
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at, model_name = self._pop_run(self._model_runs, run_id)
        duration = _duration_ms(started_at)
        usage = _extract_usage(response)
        usage_fields = " ".join(
            f"{name}={value}" for name, value in sorted(usage.items())
        )
        logger.info(
            f"event=model_finished {self._base_fields()} status=ok "
            f"model={model_name} "
            f"duration_ms={duration if duration is not None else 'unknown'}"
            + (f" {usage_fields}" if usage_fields else "")
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at, model_name = self._pop_run(self._model_runs, run_id)
        duration = _duration_ms(started_at)
        logger.error(
            f"event=model_finished {self._base_fields()} status=error "
            f"model={model_name} "
            f"duration_ms={duration if duration is not None else 'unknown'} "
            f"error_type={type(error).__name__}"
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = str(serialized.get("name") or "unknown")
        with self._lock:
            self._tool_runs[run_id] = (perf_counter(), tool_name)
        argument_names = sorted(inputs.keys()) if isinstance(inputs, dict) else []
        logger.info(
            f"event=tool_started {self._base_fields()} tool={tool_name} "
            "arg_fields="
            + json.dumps(argument_names, ensure_ascii=True, separators=(",", ":"))
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at, tool_name = self._pop_run(self._tool_runs, run_id)
        duration = _duration_ms(started_at)
        logger.info(
            f"event=tool_finished {self._base_fields()} status=ok "
            f"tool={tool_name} "
            f"duration_ms={duration if duration is not None else 'unknown'}"
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at, tool_name = self._pop_run(self._tool_runs, run_id)
        duration = _duration_ms(started_at)
        logger.error(
            f"event=tool_finished {self._base_fields()} status=error "
            f"tool={tool_name} "
            f"duration_ms={duration if duration is not None else 'unknown'} "
            f"error_type={type(error).__name__}"
        )


def log_request_started(context: RequestContext) -> float:
    logger.info(
        f"event=request_started request_id={context.request_id} "
        f"user_ref={context.user_ref} conversation_ref={context.conversation_ref}"
    )
    return perf_counter()


def log_request_finished(
    context: RequestContext,
    started_at: float,
    *,
    error: BaseException | None = None,
) -> None:
    status = "error" if error is not None else "ok"
    error_field = f" error_type={type(error).__name__}" if error else ""
    log_method = logger.error if error is not None else logger.info
    log_method(
        f"event=request_finished request_id={context.request_id} "
        f"user_ref={context.user_ref} conversation_ref={context.conversation_ref} "
        f"status={status} duration_ms={_duration_ms(started_at)}{error_field}"
    )
