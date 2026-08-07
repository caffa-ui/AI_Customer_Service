from typing import Optional
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from app.agent.agent_config.llm_config import llm
from app.agent.memory import (
    KEEP_TURNS,
    MAX_SUMMARY_CHARS,
    MIN_TOKENS_TO_COMPRESS,
)
from app.agent.State.state import SCRMState


def find_cut_off_index(messages: list, keep_turns: int = KEEP_TURNS) -> Optional[int]:
    """
    从尾部向前扫描"无tool_calls的AIMessage"（代表一轮对话彻底完成的标志）。
    数到第 keep_turns+1 个时，把它之后的位置作为切割点。

    这样切割点永远落在"一轮完整对话刚收尾"之后，结构上保证绝不会打断
    任何 AIMessage(tool_calls) 与 ToolMessage 的配对，不需要额外的孤儿消息保护逻辑。
    同时天然不受"人工审批插入HumanMessage"等中间态干扰，因为只统计真正收尾的轮次。

    返回 None 表示完整轮次不足 keep_turns+1，不应触发压缩。
    """
    final_ai_count = 0

    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            final_ai_count += 1
            if final_ai_count == keep_turns + 1:
                return i + 1  # 切割点紧跟在这条"边界轮"的最终回复之后

    return None


def message_to_text(m) -> Optional[str]:
    """
    把消息转成可读文本用于摘要。
    优先取字符串content；如果是带tool_calls的AI消息（content常为空），
    则记录调用了哪些工具，避免摘要丢失关键信息。
    """
    if isinstance(m, ToolMessage) and m.content:
        return f"tool_result(工具已确认): {m.content}"
    if isinstance(m.content, str) and m.content:
        return f"{m.type}: {m.content}"
    if hasattr(m, "tool_calls") and m.tool_calls:
        calls = ", ".join(tc["name"] for tc in m.tool_calls)
        return f"{m.type}: [调用了工具: {calls}]"
    if isinstance(m.content, list) and m.content:
        # 兜底：内容是结构化列表（如某些 ToolMessage/多模态内容），转成字符串避免丢失
        return f"{m.type}: {str(m.content)}"
    return None


def summarize_node(state: SCRMState):
    """
    高度定制的记忆压缩节点（最终版：按"完整对话轮次"切割）：
    由外部条件边触发，流程走到这里时默认已处于 Token 超载状态。

    职责：
      1. 精准保留最近 KEEP_TURNS 轮完整对话（以"无tool_calls的最终AIMessage"为轮次收尾标志）；
      2. 将更早的历史消息总结后物理删除；
      3. 切割点天然落在轮次收尾处，结构上杜绝 tool_calls 与 ToolMessage 被拆断的孤儿问题；
      4. 保护全局 SystemMessage，绝不误删；
      5. 对 LLM 调用失败、消息缺失 id 等异常情况做防御，避免死循环或崩溃。
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")

    # ========= 0. 轻量级二次确认（防御外部触发条件出错导致误删） =========
    approx_tokens = count_tokens_approximately(messages)
    if approx_tokens < MIN_TOKENS_TO_COMPRESS:
        print(f"[Summarize Node] 警告：当前仅约 {approx_tokens} tokens，明显未达压缩标准，"
              f"可能是外部触发条件有误，跳过本次压缩。")
        return {}

    print(f"\n[Summarize Node] 接收到超载信号（约 {approx_tokens} tokens），启动记忆切割与压缩...")

    # ========= 1. 精准定位：按完整对话轮次寻找切割点 =========
    cut_off_index = find_cut_off_index(messages, keep_turns=KEEP_TURNS)

    if cut_off_index is None:
        print(f"[Summarize Node] 拦截：完整对话轮次不足 {KEEP_TURNS} 轮，跳过压缩。")
        return {}

    # ========= 2. 执行切割 =========
    old_messages = messages[:cut_off_index]

    if not old_messages:
        print("[Summarize Node] 提示：暂无可压缩的旧消息，跳过本次压缩。")
        return {}

    # 把待总结的旧消息转成可读文本（保留工具调用信息，避免丢失）
    old_messages_text = "\n".join(filter(None, [message_to_text(m) for m in old_messages]))

    if not old_messages_text:
        print("[Summarize Node] 提示：待压缩内容为空，跳过本次压缩。")
        return {}

    # ========= 3. 呼叫大模型生成新摘要 =========
    summary_prompt = f"""
    你是一个企业级 SCRM 系统的记忆压缩引擎。
    请合并【之前的摘要】和【待压缩的历史聊天记录】，生成一份可供后续智能体直接使用的全新摘要。

    【记忆规则】
    1. 保留用户明确表达的偏好、预算、禁忌和目标。
    2. 保留订单号、工单号、已尝试的排障步骤、当前进度和待处理事项。
    3. 标记为“tool_result(工具已确认)”的内容可视为系统已确认事实；用户自述必须明确标注为“用户自述”。
    4. 不要把模型推测、推荐话术或未被用户/工具确认的内容写成事实。
    5. 不保存 API Key、数据库密码、完整日志或其他与后续服务无关的敏感信息。
    6. 摘要不超过 {MAX_SUMMARY_CHARS} 个字符，无内容的分类可以省略。

    【固定结构】
    【用户画像与偏好】
    【已确认事实】
    【订单与工单】
    【当前进度】
    【待处理事项】

    【之前的摘要】：{current_summary if current_summary else "暂无历史摘要"}

    【待压缩的历史聊天记录】：
    {old_messages_text}

    请直接输出全新的摘要，不要包含任何额外解释。
    """

    try:
        response = llm.invoke([SystemMessage(content=summary_prompt)])
        new_summary = response.content.strip()
    except Exception as e:
        print(f"[Summarize Node] 摘要生成失败，跳过本次压缩：{e}")
        return {}

    if not new_summary:
        print("[Summarize Node] 警告：模型返回了空摘要，跳过本次压缩以避免丢失历史信息。")
        return {}

    if len(new_summary) > MAX_SUMMARY_CHARS:
        print(
            f"[Summarize Node] 警告：摘要超过 {MAX_SUMMARY_CHARS} 字符，已截断到配置上限。"
        )
        new_summary = new_summary[:MAX_SUMMARY_CHARS].rstrip()

    # ========= 4. 生成删除指令（保护全局 SystemMessage，绝不删除） =========
    delete_commands = [
        RemoveMessage(id=m.id)
        for m in old_messages
        if m.id and not isinstance(m, SystemMessage)
    ]

    skipped = len(old_messages) - len(delete_commands)
    if skipped > 0:
        print(f"[Summarize Node] 警告：有 {skipped} 条消息因缺失 id 或属于 SystemMessage 未被删除，"
              f"如果是缺失id导致，请检查消息构造流程，可能导致重复压缩。")

    print(f"[Summarize Node] 压缩完毕！保留了最近 {KEEP_TURNS} 轮完整对话，"
          f"总结并删除了 {len(delete_commands)} 条旧消息。")

    # ========= 5. 更新状态字典 =========
    return {
        "summary": new_summary,
        "messages": delete_commands
    }
