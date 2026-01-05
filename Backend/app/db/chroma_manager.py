import os
import shutil
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from app.core.config import settings


class ChromaManager:
    def __init__(self):
        """
        初始化 ChromaDB 向量数据库
        使用 OpenAI-compat Embedding 接口进行向量化（可选）。
        """
        # 1. 数据库持久化路径
        self.persist_dir = settings.CHROMA_DB_PATH

        # 2. 延迟初始化：避免因缺少 Embedding 配置导致整个后端无法启动
        self.embedding_fn = None
        self.vector_store = None

        try:
            self._init_vector_store()
        except Exception as e:
            # 不阻塞启动：RAG 会降级为空结果
            print(f"⚠️ [ChromaDB] 向量库未启用（将降级为空检索）: {e}")

    def _init_vector_store(self):
        """按需初始化向量库；允许在缺配置时延迟失败。"""
        if self.vector_store is not None:
            return

        if not settings.BAAI_API_KEY:
            raise ValueError("未配置 BAAI_API_KEY")
        if not settings.EMBEDDING_MODEL:
            raise ValueError("未配置 EMBEDDING_MODEL")
        if not settings.EMBEDDING_BASE_URL:
            raise ValueError("未配置 EMBEDDING_BASE_URL")

        # 虽然类名是 OpenAIEmbeddings，但只要 base_url/参数兼容即可
        self.embedding_fn = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.BAAI_API_KEY,
            openai_api_base=settings.EMBEDDING_BASE_URL,
        )

        self.vector_store = Chroma(
            persist_directory=self.persist_dir,
            embedding_function=self.embedding_fn,
            collection_name="weibo_audit_rules",
        )
        print(f"✅ [ChromaDB] 向量库加载成功，路径: {self.persist_dir}")

    def add_documents(self, documents: List[Document]):
        """
        [知识库构建] 将数据写入向量库
        """
        if not documents:
            return

        print(
            f"📥 [ChromaDB] 正在写入 {len(documents)} 条数据 (Model: {settings.EMBEDDING_MODEL})..."
        )
        try:
            self.vector_store.add_documents(documents)
            print("✅ [ChromaDB] 写入完成")
        except Exception as e:
            print(f"❌ [ChromaDB] 写入失败 (可能是网络或Key的问题): {e}")

    def search_related_laws(
        self, query: str, top_k: int = 3, category_filter: str = None
    ) -> List[Document]:
        """
        检索规则（支持 纯向量检索 OR 标签过滤检索）
        :param query: 搜索词（可以是用户的话，也可以是标签）
        :param top_k: 返回数量
        :param category_filter: (可选) 强制限定的大类标签，如 "违法信息-色情"
        """
        try:
            if self.vector_store is None:
                self._init_vector_store()

            # 1. 如果有标签过滤器，使用 metadata 过滤
            if category_filter:
                print(f"🎯 [RAG] 启用精准过滤: category == '{category_filter}'")
                # Chroma 的 filter 语法: where={"key": "value"}
                # 这里的 query 依然可以用，会在过滤后的范围内再做一次相似度排序
                return self.vector_store.similarity_search(
                    query, k=top_k, filter={"category": category_filter}
                )

            # 2. 如果没有标签，回退到全局搜索（兜底）
            else:
                return self.vector_store.similarity_search(query, k=top_k)

        except Exception as e:
            print(f"⚠️ [RAG] 检索出错: {e}")
            return []

    def clear_db(self):
        """
        [最小更改版] 清空数据库
        策略：不删文件夹，只删里面的数据。
        """
        if self.vector_store is None:
            return

        print("⚠️ [ChromaDB] 正在清空现有规则...")
        try:
            # 1. 获取库里所有数据的 ID
            all_data = self.vector_store.get()
            ids = all_data["ids"]

            # 2. 如果有数据，就根据 ID 全部删除
            if ids:
                self.vector_store.delete(ids=ids)
                print(f"🗑️ [ChromaDB] 已清除 {len(ids)} 条历史数据")
            else:
                print("🗑️ [ChromaDB] 数据库已经是空的，无需清理")

        except Exception as e:
            print(f"⚠️ [ChromaDB] 清理过程遇到错误 (可忽略): {e}")


# 单例导出
chroma_db = ChromaManager()
