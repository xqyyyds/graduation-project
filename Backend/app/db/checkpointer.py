import sqlite3
from contextlib import contextmanager
from langgraph.checkpoint.sqlite import SqliteSaver
from app.core.config import settings

# 定义 SQLite 文件路径 (从配置读取)
DB_PATH = settings.CHECKPOINT_DB_PATH


class CheckpointerManager:
    """
    负责管理 LangGraph 的状态持久化 (Checkpointing)。
    实现“断点续传”和“会话记忆”的核心组件。
    """

    @contextmanager
    def get_checkpointer(self):
        """
        上下文管理器：提供一个可用的 SqliteSaver 实例。
        用法：
        with checkpointer_manager.get_checkpointer() as checkpointer:
            app = workflow.compile(checkpointer=checkpointer)
        """
        # check_same_thread=False 允许在多线程环境(如FastAPI)中使用
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        try:
            # 这里的 SqliteSaver 是 LangGraph 自带的神器
            # 它会自动在 SQLite 里建表，存 State 快照
            yield SqliteSaver(conn)
        finally:
            conn.close()


# 单例导出
checkpointer_manager = CheckpointerManager()
