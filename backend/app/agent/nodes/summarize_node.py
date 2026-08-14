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
    """ 获取消息切割的下表 """
    final_ai_count = 0

    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            final_ai_count += 1
            if final_ai_count == keep_turns + 1:
                return i + 1
    return None


def message_to_text(m) -> Optional[str]:
    """获取消息中的可读文本content"""
    if isinstance(m, ToolMessage) and m.content:
        return f"tool_result(工具已确认): {m.content}"
    if isinstance(m.content, str) and m.content:
        return f"{m.type}: {m.content}"
    if hasattr(m, "tool_calls") and m.tool_calls:
        calls = ", ".join(tc["name"] for tc in m.tool_calls)
        return f"{m.type}: [调用了工具: {calls}]"
    if isinstance(m.content, list) and m.content:
        # 将如图片等非文本转成字符串避免丢失
        return f"{m.type}: {str(m.content)}"
    return None


def summarize_node(state: SCRMState):
    """
     按照基本的总结格式，并有基本的防错，减少token消耗的机制
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")

    # 防错
    approx_tokens = count_tokens_approximately(messages)
    if approx_tokens < MIN_TOKENS_TO_COMPRESS:
        print(f"[Summarize Node] 警告：当前仅约 {approx_tokens} tokens，明显未达压缩标准，"
              f"可能是外部触发条件有误，跳过本次压缩。")
        return {}

    print(f"\n[Summarize Node] 消息token超出阈值（约 {approx_tokens} tokens），需要进行记忆切割与压缩...")

    cut_off_index = find_cut_off_index(messages, keep_turns=KEEP_TURNS)

    if cut_off_index is None:
        print(f"[Summarize Node] 拦截：完整对话轮次不足 {KEEP_TURNS} 轮，跳过压缩。")
        return {}

    old_messages = messages[:cut_off_index]

    if not old_messages:
        print("[Summarize Node] 提示：暂无可压缩的旧消息，跳过本次压缩。")
        return {}

    old_messages_text = "\n".join(filter(None, [message_to_text(m) for m in old_messages]))

    if not old_messages_text:
        print("[Summarize Node] 提示：待压缩内容为空，跳过本次压缩。")
        return {}

    summary_prompt = f"""
    你是一个企业级 SCRM 系统的记忆压缩引擎。
    请合并【之前的摘要】和【待压缩的历史聊天记录】，生成一份可供后续智能体直接使用的全新摘要。

    【记忆规则】
    1. 保留用户明确表达的偏好、预算、禁忌和目标。
    2. 保留订单号、工单号、已尝试的排障步骤、当前进度和待处理事项。
    3. 标记为“tool_result(工具已确认)”的内容可视为系统已确认事实；用户自述必须明确标注为“用户自述”。
    4. 不要把模型推测、推荐话术或未被用户/工具确认的内容写成事实。
    5. 不保存 API Key、数据库密码、完整日志或其他与后续服务无关的敏感信息。
    6. 摘要不超过 {MAX_SUMMARY_CHARS},最好控制在{MAX_SUMMARY_CHARS-1000}个字符之内，无内容的分类可以省略。

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
        print(f"[Summarize Node] 摘要生成失败，跳过本次压缩，错误：{e}")
        return {}

    if not new_summary:
        print("[Summarize Node] 警告：模型返回了空摘要，跳过本次压缩以避免丢失历史信息。")
        return {}

    #防止超出上限，强制切断(一般不会，这里使用者可以通过优化提示词来避免，我的提示词只是针对我的项目测试设置)
    if len(new_summary) > MAX_SUMMARY_CHARS:
        print(
            f"[Summarize Node] 警告：摘要超过 {MAX_SUMMARY_CHARS} 字符，已截断到配置上限。"
        )
        new_summary = new_summary[:MAX_SUMMARY_CHARS].rstrip()
    #删除指令打包，后续统一返回执行
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

    return {
        "summary": new_summary,
        "messages": delete_commands
    }
