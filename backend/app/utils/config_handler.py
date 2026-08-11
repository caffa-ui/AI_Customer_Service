import yaml
from app.utils.path_tool import get_abs_path


class Config(dict):

    def __call__(self, key: str, default=None):
        if key in self:
            return self[key]
        if default is not None:
            return default
        raise KeyError(f"配置项不存在: {key}")


def _load_yaml(config_path: str, encoding: str = "utf-8") -> Config:
    with open(config_path,"r",encoding=encoding) as f:
        content = yaml.safe_load(f) or {}
    if not isinstance(content, dict):
        raise ValueError(f"配置文件根节点必须是字典: {config_path}")
    return Config(content)


def load_rag_config(config_path: str=get_abs_path("config/rag.yaml"),encoding: str="utf-8"):
    return _load_yaml(config_path, encoding)


def load_chroma_config(config_path: str = get_abs_path("config/chroma.yaml"), encoding: str = "utf-8"):
    return _load_yaml(config_path, encoding)


def load_prompt_config(config_path: str = get_abs_path("config/prompt.yaml"), encoding: str = "utf-8"):
    return _load_yaml(config_path, encoding)


def load_agent_config(config_path: str = get_abs_path("config/agent.yaml"), encoding: str = "utf-8"):
    return _load_yaml(config_path, encoding)

rag_config=load_rag_config()
chroma_config=load_chroma_config()
prompt_config=load_prompt_config()
agent_config=load_agent_config()
