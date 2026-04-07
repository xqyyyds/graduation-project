# app/services/category_classifier.py
"""
热搜分类服务：对热搜词条进行类别标注
支持的类别：社会、高校、生活、科技、政治、其他
"""
import concurrent.futures
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm_factory import get_main_llm
from app.core.logger import logger


# =====================================================
# 1. 分类结果 Schema
# =====================================================
class CategoryResult(BaseModel):
    """单个热搜的分类结果"""

    word: str = Field(..., description="热搜词条原文")
    category: str = Field(
        ...,
        description="分类结果，必须从以下选项中选择：社会、高校、生活、科技、政治、其他",
    )
    reasoning: str = Field(..., description="分类理由，一句话说明")


class BatchCategoryResult(BaseModel):
    """批量分类结果"""

    results: List[CategoryResult] = Field(..., description="分类结果列表")


# =====================================================
# 2. 分类 Prompt
# =====================================================
CATEGORY_CLASSIFY_PROMPT = """你是一名热搜分类专家。请对以下热搜词条进行分类。

可选类别（必须严格从中选择）：
1. 社会 - 社会事件、民生新闻、公共安全、司法案件、突发事故等
2. 高校 - 大学、高考、研究生、学术、校园事件、教育政策等
3. 生活 - 娱乐、明星、美食、旅游、消费、健康养生、情感等
4. 科技 - 科技产品、互联网、人工智能、航天、新能源、数码等
5. 政治 - 国内政策、国际关系、外交、军事、领导人活动、地缘政治等
6. 其他 - 无法归入以上类别的内容

热搜词条：
{word}

请判断该词条属于哪个类别，并给出简短理由。
"""

BATCH_CATEGORY_PROMPT = """你是一名热搜分类专家。请对以下热搜词条逐一进行分类。

可选类别（必须严格从中选择）：
1. 社会 - 社会事件、民生新闻、公共安全、司法案件、突发事故等
2. 高校 - 大学、高考、研究生、学术、校园事件、教育政策等
3. 生活 - 娱乐、明星、美食、旅游、消费、健康养生、情感等
4. 科技 - 科技产品、互联网、人工智能、航天、新能源、数码等
5. 政治 - 国内政策、国际关系、外交、军事、领导人活动、地缘政治等
6. 其他 - 无法归入以上类别的内容

待分类的热搜词条列表：
{words_list}

请为每个词条判断类别，输出完整的分类结果列表。
"""


# =====================================================
# 3. 分类服务类
# =====================================================
class CategoryClassifier:
    """热搜分类器"""

    # 有效类别列表
    VALID_CATEGORIES = ["社会", "高校", "生活", "科技", "政治", "其他"]

    def __init__(self):
        self.llm = get_main_llm(
            temperature=0.1,
            request_timeout=60,
            max_retries=2,
        )
        self.single_llm = self.llm.with_structured_output(CategoryResult)
        self.batch_llm = self.llm.with_structured_output(BatchCategoryResult)

        self.single_prompt = ChatPromptTemplate.from_template(CATEGORY_CLASSIFY_PROMPT)
        self.batch_prompt = ChatPromptTemplate.from_template(BATCH_CATEGORY_PROMPT)

    def classify_single(self, word: str) -> Optional[str]:
        """
        对单个热搜词条进行分类

        :param word: 热搜词条
        :return: 分类结果（社会/高校/生活/科技/政治/其他）
        """
        try:
            chain = self.single_prompt | self.single_llm
            result = chain.invoke({"word": word})

            if result and result.category in self.VALID_CATEGORIES:
                logger.debug(f"   [分类] {word} -> {result.category}")
                return result.category
            else:
                logger.warning(f"   [分类] {word} -> 无效结果，归为其他")
                return "其他"

        except Exception as e:
            logger.error(f"   [分类] {word} 分类失败: {e}")
            return "其他"

    def classify_batch(self, words: List[str], batch_size: int = 10) -> Dict[str, str]:
        """
        批量分类热搜词条（使用批处理减少 API 调用）

        :param words: 热搜词条列表
        :param batch_size: 每批处理的数量
        :return: {词条: 类别} 字典
        """
        results = {}

        # 分批处理
        for i in range(0, len(words), batch_size):
            batch = words[i : i + batch_size]
            words_text = "\n".join([f"{j+1}. {w}" for j, w in enumerate(batch)])

            try:
                chain = self.batch_prompt | self.batch_llm
                batch_result = chain.invoke({"words_list": words_text})

                if batch_result and batch_result.results:
                    for item in batch_result.results:
                        cat = (
                            item.category
                            if item.category in self.VALID_CATEGORIES
                            else "其他"
                        )
                        results[item.word] = cat

            except Exception as e:
                logger.error(f"   [批量分类] 批次 {i//batch_size + 1} 失败: {e}")
                # 降级为单条处理
                for w in batch:
                    if w not in results:
                        results[w] = self.classify_single(w)

        return results

    def classify_parallel(
        self,
        words: List[str],
        max_workers: int = 8,
        existing_categories: Optional[Dict[str, str]] = None,
        batch_size: int = 20,
    ) -> Dict[str, str]:
        """
        并行分类热搜词条

        :param words: 热搜词条列表
        :param max_workers: 最大并发数
        :param existing_categories: 已有分类结果，跳过已分类的词条
        :return: {词条: 类别} 字典
        """
        existing = existing_categories or {}

        # 过滤出需要分类的词条
        to_classify = [w for w in words if w not in existing or not existing.get(w)]

        if not to_classify:
            logger.info("   [分类] 所有词条已有分类，跳过")
            return existing

        logger.info(
            f"   [分类] 需要分类 {len(to_classify)} 个词条（已有 {len(existing)} 个）..."
        )

        results = dict(existing)  # 复制已有结果
        batches = [
            to_classify[i : i + batch_size]
            for i in range(0, len(to_classify), batch_size)
        ]
        worker_count = min(max_workers, max(1, len(batches), 4))

        logger.info(
            f"   [分类] 批量模式启动：{len(batches)} 批，每批最多 {batch_size} 个词条，并发 {worker_count}"
        )

        def process_batch(batch_words: List[str]) -> Dict[str, str]:
            return self.classify_batch(batch_words, batch_size=len(batch_words))

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_batch_idx = {
                executor.submit(process_batch, batch): idx
                for idx, batch in enumerate(batches, start=1)
            }

            completed = 0
            for future in concurrent.futures.as_completed(future_to_batch_idx):
                batch_idx = future_to_batch_idx[future]
                try:
                    batch_result = future.result()
                    results.update(batch_result)
                except Exception as e:
                    logger.error(f"   [分类] 批次 {batch_idx} 并行处理失败: {e}")
                    for word in batches[batch_idx - 1]:
                        if word not in results:
                            results[word] = "其他"
                completed += 1
                if completed == len(batches) or completed % 5 == 0:
                    logger.info(f"   [分类] 批量进度: {completed}/{len(batches)} 批已完成")

        logger.info(f"   [分类] 完成，共 {len(results)} 个词条")
        return results


# 单例导出
category_classifier = CategoryClassifier()
