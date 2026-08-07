import asyncio
import os
from pathlib import Path
import selectors
import sys


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.chat.runtime import create_chat_service


async def run_cli() -> None:
    user_id = (os.getenv("CLI_USER_ID") or "cli-user").strip()
    conversation_id = (
        os.getenv("CLI_CONVERSATION_ID") or "cli-default"
    ).strip()

    async with create_chat_service() as chat_service:
        print(
            "SCRM AI 客服已启动。"
            f"当前会话: {conversation_id}；输入 exit 或 quit 退出。"
        )
        while True:
            try:
                user_input = input("\n用户: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                print("已退出。")
                break

            try:
                response = await chat_service.chat(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message=user_input,
                )
                print(f"AI: {response.content}")
            except Exception as exc:
                print(f"AI 调用失败: {exc}")


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            # psycopg 的异步连接不支持 Windows 默认 ProactorEventLoop。
            # 显式使用 SelectorEventLoop，CLI 与未来 FastAPI 的异步数据库
            # 调用才能共用同一套 ChatService。
            with asyncio.Runner(
                loop_factory=lambda: asyncio.SelectorEventLoop(
                    selectors.SelectSelector()
                )
            ) as runner:
                runner.run(run_cli())
        else:
            asyncio.run(run_cli())
    except RuntimeError as exc:
        print(f"启动失败: {exc}")
        raise SystemExit(1) from exc
