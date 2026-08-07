import asyncio
import os
from pathlib import Path
import selectors
import sys

from dotenv import load_dotenv
import uvicorn


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
ENV_PATH = BACKEND_DIR / ".env"


def _api_port() -> int:
    raw_value = (os.getenv("API_PORT") or "8000").strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("API_PORT 必须是 1 到 65535 之间的整数") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("API_PORT 必须是 1 到 65535 之间的整数")
    return port


def _windows_selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def main() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
    host = (os.getenv("API_HOST") or "127.0.0.1").strip()
    if not host:
        raise RuntimeError("API_HOST 不能为空")

    loop = _windows_selector_loop if sys.platform == "win32" else "auto"
    uvicorn.run(
        "app.api.main:app",
        app_dir=str(BACKEND_DIR),
        host=host,
        port=_api_port(),
        loop=loop,
        workers=1,
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"启动失败: {exc}")
        raise SystemExit(1) from exc
