from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model


# 明确读取 backend/.env，避免启动目录不同时找错配置文件。
# 部署环境变量优先，便于后续由 FastAPI/Uvicorn 注入配置。
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

llm=init_chat_model(
    "deepseek-v4-pro",
    model_provider="deepseek",
    temperature=0
)
