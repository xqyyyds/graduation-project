import os
from dotenv import load_dotenv

# 让 .env 文件的值优先于系统环境变量
load_dotenv(override=True)


class Settings:
    # llm设置
    #  切换为火山引擎 DeepSeek-V3
    ZHIPU_API_KEY: str = os.getenv(
        "ZHIPU_API_KEY", "bad91148-3e61-4cb2-9615-3b838333849c"
    )
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v3-2-251201")
    # 火山引擎 Ark OpenAI-compat base url
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

    # embedding设置
    BAAI_API_KEY = os.getenv("BAAI_API_KEY", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")

    # 数据库设置
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    # 日志设置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "media_crawler_db")
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")

    # Checkpoint设置 (从 .env 读取，或指向项目根目录)
    # 这里我们用一个基于 __file__ 的绝对路径做兜底，确保文件不会随便乱跑
    _PROJECT_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    CHECKPOINT_DB_PATH = os.getenv(
        "CHECKPOINT_DB_PATH", os.path.join(_PROJECT_ROOT, "checkpoints.sqlite")
    )

    # Tavily设置
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    #  调试开关：强制覆盖审核结果 (即使已审核过也重新审)
    FORCE_AUDIT_UPDATE: bool = os.getenv("FORCE_AUDIT_UPDATE", "True").lower() == "true"


settings = Settings()
