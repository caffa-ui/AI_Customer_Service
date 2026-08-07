from functools import lru_cache

from app.utils.logger_handler import get_logger
from app.utils.config_handler import prompt_config
from app.utils.path_tool import get_abs_path

logger = get_logger("prompt_handler")

@lru_cache(maxsize=None)
def _load_prompt_by_key(prompt_key: str) -> str:
    try:
        prompt_path = get_abs_path(prompt_config[prompt_key])
    except Exception as e:
        logger.error(f"在prompt.yaml中不存在 {prompt_key} 的配置项, {str(e)}")
        raise e

    try:
        with open(prompt_path, 'r', encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"读取或解析文件出错: {prompt_path}, {str(e)}")
        raise e

def load_supervisor_prompt() -> str:
    return _load_prompt_by_key("supervisor_prompt")

def load_support_prompt() -> str:
    return _load_prompt_by_key("support_prompt")

def load_sale_prompt() -> str:
    return _load_prompt_by_key("sale_prompt")

def load_rag_prompt() -> str:
    return _load_prompt_by_key("rag_prompt")
