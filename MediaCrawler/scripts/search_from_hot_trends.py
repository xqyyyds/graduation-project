"""
Read latest hot_trends from MongoDB (always take newest batch) and trigger Weibo search crawler
for those keywords. Designed to run right after hot-trends collection.

Usage:
  uv run python scripts/search_from_hot_trends.py
    uv run python scripts/search_from_hot_trends.py --limit 50

Behavior:
- Query media_crawler_db.hot_trends for the latest batch, take up to `--limit` keywords (no rank needed)
- Set config.KEYWORDS to a comma-separated list of keywords
- Force config.CRAWLER_MAX_NOTES_COUNT=50 and config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES=100
- Run the Weibo crawler (`WeiboCrawler.start`) which will perform searches

"""

import argparse
import asyncio
from pymongo import MongoClient
from typing import Dict, List, Optional, Tuple
import config
from media_platform.weibo.core import WeiboCrawler
from tools import utils
from config.db_config import MONGO_URI


def fetch_hot_keywords_with_ids(
    mongo_uri: str, limit: int = 50
) -> Tuple[List[str], Dict[str, object]]:
    """Fetch up to `limit` latest keywords and their hot_trends _id.

    Returns:
        keywords: List[str] (pure keyword text)
        keyword_to_hot_trend_id: Dict[str, ObjectId]
    """
    client = MongoClient(mongo_uri)
    db = client["media_crawler_db"]
    coll = db["hot_trends"]

    # 直接取最新的 `limit` 条，不额外扩容
    cursor = coll.find().sort([("last_collected", -1)]).limit(limit)

    seen = set()
    keywords: List[str] = []
    keyword_to_hot_trend_id: Dict[str, object] = {}
    for doc in cursor:
        ws = doc.get("word_scheme") or doc.get("word")
        if not ws:
            continue
        ws = ws.strip()
        if not ws or ws in seen:
            continue
        seen.add(ws)
        keywords.append(ws)
        if ws not in keyword_to_hot_trend_id and doc.get("_id") is not None:
            keyword_to_hot_trend_id[ws] = doc.get("_id")
        if len(keywords) >= limit:
            break

    client.close()
    return keywords, keyword_to_hot_trend_id


async def run_crawler_for_keywords(
    keywords: List[str], keyword_to_hot_trend_id: Dict[str, object]
):
    """Set config and run the WeiboCrawler to search these keywords."""
    if not keywords:
        print("No keywords to search.")
        return

    # Apply required limits for this run
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = ",".join(keywords)
    # IMPORTANT: never append hot_trend_id into keyword, it will break search.
    config.HOT_TREND_ID_BY_KEYWORD = keyword_to_hot_trend_id
    # Ensure single-level comments
    config.ENABLE_GET_SUB_COMMENTS = False

    print("🔎 Running Weibo search for keywords:")
    for k in keywords:
        print(" -", k)

    crawler = WeiboCrawler()
    await crawler.start()


def main():
    parser = argparse.ArgumentParser(
        description="Use latest hot_trends to run Weibo search crawler"
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max number of keywords to take"
    )
    parser.add_argument("--mongo", type=str, default=MONGO_URI, help="MongoDB URI")
    args = parser.parse_args()

    keywords, keyword_to_hot_trend_id = fetch_hot_keywords_with_ids(
        args.mongo, limit=args.limit
    )

    if not keywords:
        print("No keywords found for the specified date; aborting.")
        return

    # Run crawler
    asyncio.run(run_crawler_for_keywords(keywords, keyword_to_hot_trend_id))


if __name__ == "__main__":
    main()
