from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

llm = init_chat_model(
    "deepseek-v4-pro",
    model_provider="deepseek",
    temperature=0
)

small_llm = init_chat_model(
    "deepseek-v4-flash",
    model_provider="deepseek",
    temperature=0
)
