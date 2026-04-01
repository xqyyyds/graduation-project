import sys
import os

# 1. 确保路径正确，能找到 app 模块
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(root_dir)

from app.db.chroma_manager import chroma_db
from app.core.logger import logger


def check_db_status():
    logger.info("[System] 正在检查 ChromaDB 状态...")

    # 1. 检查数据总量
    # 这一步需要访问底层 collection 对象来获取计数
    try:
        count = chroma_db.vector_store._collection.count()
        logger.info(f" 当前数据库中共有规则数量: {count} 条")

        if count == 0:
            logger.warning(" 数据库是空的！请先运行 init_weibo_rules.py")
            return
    except Exception as e:
        logger.error(f" 无法获取数量 (可能是连接问题): {e}")
        return

    # 2. 校验规则库中是否存在“色情/淫秽”相关条目（避免“库里压根没写进去”的误判）
    try:
        all_data = chroma_db.vector_store.get(include=["documents", "metadatas"])
        docs = all_data.get("documents") or []
        metas = all_data.get("metadatas") or []
        porn_hits = []
        for d, m in zip(docs, metas):
            category = (m or {}).get("category", "")
            if (
                ("色情" in (d or ""))
                or ("淫秽" in (d or ""))
                or ("色情" in category)
                or ("淫秽" in category)
            ):
                porn_hits.append((d, m))
        logger.info(f"库内含'色情/淫秽'相关规则: {len(porn_hits)} 条")
        if porn_hits:
            sample_doc, sample_meta = porn_hits[0]
            logger.info(f"   示例: {sample_doc}")
            logger.info(
                f"   类别: {sample_meta.get('category')} | 条款: {sample_meta.get('article')} | 风险: {sample_meta.get('risk_level')}"
            )
    except Exception as e:
        logger.error(f" 无法抽样验证库内容: {e}")

    # 3. 多组查询对比（含分数）
    test_queries = [
        "发布黄色信息",
        "发布淫秽色情内容",
        "发福利套图引流",
        "发布裸照视频",
    ]

    logger.info(f"\n[System] 正在测试语义检索(Top5, 含分数)...")
    for test_query in test_queries:
        logger.info("\n" + "-" * 70)
        logger.info(f"Query: "{test_query}"")
        results = chroma_db.search_related_laws(test_query, top_k=5)

        if not results:
            logger.warning(" 未检索到任何结果！")
            continue

        for i, doc in enumerate(results, start=1):
            logger.info(f" 命中规则 #{i}")
            logger.info(f"   条款: {doc.metadata.get('article')}")
            logger.info(f"    类别: {doc.metadata.get('category')}")
            logger.info(f"    风险: {doc.metadata.get('risk_level')}")
            logger.info(f"    内容: {doc.page_content}")


if __name__ == "__main__":
    check_db_status()
