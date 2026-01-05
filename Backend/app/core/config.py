import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # llm设置
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "glm-4.6")
    # 智谱 OpenAI-compat base url；允许用户通过 .env 覆盖
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

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

    # Tavily设置
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


settings = Settings()
