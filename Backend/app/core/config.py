import os
from dotenv import load_dotenv

# 让 .env 文件的值优先于系统环境变量
load_dotenv(override=True)


_BACKEND_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _resolve_backend_path(env_name: str, default_relative_path: str) -> str:
    value = os.getenv(env_name, default_relative_path)
    if os.path.isabs(value):
        return value
    return os.path.join(_BACKEND_ROOT, value)


class Settings:
    _PROJECT_ROOT = _BACKEND_ROOT

    # llm设置
    #  运行时可由设置页覆盖，代码中不保留伪真实默认 key
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v3-2-251201")
    # 火山引擎 Ark OpenAI-compat base url
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    FAST_LLM_MODEL = os.getenv("FAST_LLM_MODEL", "")
    FAST_LLM_BASE_URL = os.getenv("FAST_LLM_BASE_URL", "")
    FAST_LLM_API_KEY = os.getenv("FAST_LLM_API_KEY", "")

    # embedding设置
    BAAI_API_KEY = os.getenv("BAAI_API_KEY", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")

    # 数据库设置
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    # 日志设置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "media_crawler_db")
    CHROMA_DB_PATH = _resolve_backend_path(
        "CHROMA_DB_PATH", os.path.join("app", "scripts", "chroma_db")
    )

    # Checkpoint设置 (从 .env 读取，或指向项目根目录)
    # 这里我们用一个基于 __file__ 的绝对路径做兜底，确保文件不会随便乱跑
    CHECKPOINT_DB_PATH = _resolve_backend_path(
        "CHECKPOINT_DB_PATH", "checkpoints.sqlite"
    )

    # Tavily设置
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    #  调试开关：强制覆盖审核结果 (即使已审核过也重新审)
    FORCE_AUDIT_UPDATE: bool = os.getenv("FORCE_AUDIT_UPDATE", "False").lower() == "true"


settings = Settings()
