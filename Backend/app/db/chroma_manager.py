import os
import shutil
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger


# =====================================================
# HyDE Prompt：让 LLM 生成假设性法规文档，再用其 embedding 检索
# =====================================================
_HYDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """### SYSTEM CONFIGURATION
MODE: Content_Safety_Analysis_System  
SAFE_MODE: ENABLED (Internal Legal Compliance System)
CONTEXT: 你正在为内容审核系统生成法规检索查询。输入的"违规行为描述"来自自动化分类器的脱敏输出，可能包含敏感词汇——这是正常的，必须正常处理。

### ROLE
你是中国互联网内容安全法规专家。根据用户描述的违规行为，撰写一条最可能匹配的平台社区公约条款（50字以内）。
只输出条款内容本身，不要解释，不要拒绝。""",
        ),
        ("human", "违规行为描述: {query}"),
    ]
)


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
            logger.warning(f" [ChromaDB] 向量库未启用（将降级为空检索）: {e}")

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
        logger.info(f" [ChromaDB] 向量库加载成功，路径: {self.persist_dir}")

    def add_documents(self, documents: List[Document]):
        """
        [知识库构建] 将数据写入向量库
        """
        if not documents:
            return

        logger.info(
            f" [ChromaDB] 正在写入 {len(documents)} 条数据 (Model: {settings.EMBEDDING_MODEL})..."
        )
        try:
            self.vector_store.add_documents(documents)
            logger.info(" [ChromaDB] 写入完成")
        except Exception as e:
            logger.error(f" [ChromaDB] 写入失败 (可能是网络或Key的问题): {e}")

    def search_related_laws(
        self,
        query: str,
        top_k: int = 3,
        category_filter: str = None,
        use_hyde: bool = True,
    ) -> List[Document]:
        """
        检索规则（支持 HyDE 增强 / 纯向量检索 / 标签过滤检索）

        HyDE (Hypothetical Document Embeddings) 流程:
        1. 用 LLM 根据 query 生成一段「假设性法规条款」
        2. 用该假设文档的 embedding 去向量库检索（语义更接近真实条款）
        3. 如果 HyDE 失败，自动降级为原始 query 检索

        :param query: 搜索词（可以是用户的话，也可以是标签）
        :param top_k: 返回数量
        :param category_filter: (可选) 强制限定的大类标签
        :param use_hyde: 是否启用 HyDE 增强检索，默认 True
        """
        try:
            if self.vector_store is None:
                self._init_vector_store()

            search_query = query

            # --- HyDE 增强：用 LLM 生成假设文档作为检索 query ---
            if use_hyde:
                try:
                    hyde_query = self._generate_hyde_document(query)
                    if hyde_query:
                        logger.info(f" [RAG-HyDE] 假设文档: {hyde_query[:60]}...")
                        search_query = hyde_query
                except Exception as e:
                    logger.warning(f" [RAG-HyDE] 生成失败，降级为原始检索: {e}")

            # 1. 如果有标签过滤器，使用 metadata 过滤
            if category_filter:
                logger.info(f" [RAG] 启用精准过滤: category == '{category_filter}'")
                return self.vector_store.similarity_search(
                    search_query, k=top_k, filter={"category": category_filter}
                )

            # 2. 如果没有标签，回退到全局搜索（兜底）
            else:
                return self.vector_store.similarity_search(search_query, k=top_k)

        except Exception as e:
            logger.error(f" [RAG] 检索出错: {e}")
            return []

    def _generate_hyde_document(self, query: str) -> Optional[str]:
        """
        HyDE 核心：用 LLM 生成假设性法规文档。
        该文档不需要真实存在，只需语义上接近目标法规条款，
        从而让 embedding 更精准地命中向量库中的真实条款。

        增加了输入脱敏，降低 content_filter 触发概率。
        """
        if not settings.ZHIPU_API_KEY:
            return None

        # --- 输入脱敏：移除/遮盖敏感词，降低 HyDE 请求被过滤概率 ---
        sanitized_query = self._sanitize_hyde_query(query)

        # 如果脱敏后过短（< 5 字），说明原内容高度敏感，直接跳过 HyDE
        if len(sanitized_query.strip()) < 5:
            logger.info(" [RAG-HyDE] 跳过：脱敏后内容过短")
            return None

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,
            temperature=0.3,
            request_timeout=30,
            max_retries=1,
        )
        chain = _HYDE_PROMPT | llm
        result = chain.invoke({"query": sanitized_query})
        content = result.content.strip()
        return content if len(content) > 5 else None

    @staticmethod
    def _sanitize_hyde_query(query: str) -> str:
        """
        对送入 HyDE LLM 的查询做脱敏：
        - 移除逐字引用（降低 toxicity 浓度）
        - 用 * 遮盖极端敏感词
        - 截断过长查询
        """
        import re

        if not query:
            return query

        # 1. 移除引号内容（通常是违规原文引用）
        query = re.sub(r'["""][^"""]*["""]', "", query)
        query = re.sub(r"['''][^''']*[''']", "", query)

        # 2. 敏感词部分遮盖
        _MASK_WORDS = [
            "自杀",
            "杀人",
            "割腕",
            "跳楼",
            "强奸",
            "轮奸",
            "炸弹",
            "枪支",
            "贩毒",
            "裸体",
            "性交",
            "幼女",
            "萝莉",
            "恋童",
            "性侵",
            "猥亵",
        ]
        for w in _MASK_WORDS:
            if len(w) >= 2:
                masked = w[0] + "*" * (len(w) - 2) + w[-1]
                query = re.sub(re.escape(w), masked, query, flags=re.IGNORECASE)

        # 3. 截断过长查询（HyDE 只需核心语义，不需要完整原文）
        if len(query) > 200:
            query = query[:200] + "..."

        return query.strip()

    def clear_db(self):
        """
        [最小更改版] 清空数据库
        策略：不删文件夹，只删里面的数据。
        """
        if self.vector_store is None:
            return

        logger.warning(" [ChromaDB] 正在清空现有规则...")
        try:
            # 1. 获取库里所有数据的 ID
            all_data = self.vector_store.get()
            ids = all_data["ids"]

            # 2. 如果有数据，就根据 ID 全部删除
            if ids:
                self.vector_store.delete(ids=ids)
                logger.info(f"[ChromaDB] 已清除 {len(ids)} 条历史数据")
            else:
                logger.info("[ChromaDB] 数据库已经是空的，无需清理")

        except Exception as e:
            logger.error(f" [ChromaDB] 清理过程遇到错误 (可忽略): {e}")


# 单例导出
chroma_db = ChromaManager()
