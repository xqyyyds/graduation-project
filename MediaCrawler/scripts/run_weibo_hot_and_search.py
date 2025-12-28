"""
Orchestrator: run society hot search, then search posts by those hot keywords.

Steps:
1) Run scripts/crawl_weibo_society_hot.py (requests-based) to fetch the latest hot trends.
2) Read the freshly inserted docs from Mongo (collected_at >= run start), take up to 50 `word_scheme`.
3) Set Weibo search configs and run Playwright-based Weibo crawler for those keywords
   (each keyword up to 50 posts, each post up to 100 top-level comments).

Usage:
  uv run python scripts/run_weibo_hot_and_search.py
Options:
  --mongo URI     MongoDB URI (default: mongodb://localhost:27017/)
  --limit N       Max keywords to use (default: 50)
"""

from __future__ import annotations
import argparse
import asyncio
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from pathlib import Path

# Ensure project root on sys.path before importing project modules
sys.path.append(str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient

import config
from media_platform.weibo.core import WeiboCrawler
from config.db_config import MONGO_URI
from tools import utils


def fetch_recent_keywords_with_ids(
    mongo_uri: str, since_utc: datetime, limit: int = 50
) -> Tuple[List[str], Dict[str, object]]:
    """Fetch up to `limit` distinct keywords inserted/updated since since_utc.

    Returns:
        keywords: List[str] (pure keyword text)
        keyword_to_hot_trend_id: Dict[str, ObjectId]
    """
    client = MongoClient(mongo_uri)
    coll = client["media_crawler_db"]["hot_trends"]
    since_str = utils.to_china_time_str(since_utc, with_tz=True)
    cursor = (
        coll.find({"last_collected": {"$gte": since_str}})
        .sort([("rank", 1), ("last_collected", -1)])
        .limit(limit * 2)
    )
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


async def run_search(keywords: List[str], keyword_to_hot_trend_id: Dict[str, object]):
    if not keywords:
        print("No keywords to search; skipping crawler.")
        return

    # Apply limits for this run
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = ",".join(keywords)
    # IMPORTANT: never append hot_trend_id into keyword, it will break search.
    config.HOT_TREND_ID_BY_KEYWORD = keyword_to_hot_trend_id
    config.ENABLE_GET_SUB_COMMENTS = False

    print("🔎 Weibo search with keywords (top {}):".format(len(keywords)))
    for k in keywords:
        print(" -", k)

    crawler = WeiboCrawler()
    try:
        await crawler.start()
    finally:
        # Ensure browser context and other resources are closed even if start() raises
        try:
            await crawler.close()
        except Exception as e:
            print(f"Warning: error while closing crawler resources: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run hot-trends then search by those keywords"
    )
    parser.add_argument("--mongo", type=str, default=MONGO_URI, help="MongoDB URI")
    parser.add_argument(
        "--limit", type=int, default=50, help="Max keywords to use from hot trends"
    )
    args = parser.parse_args()

    china_tz = timezone(timedelta(hours=8))
    run_start = datetime.now(china_tz)

    # Step 1: run society hot crawler (requests-based)
    print("🚀 Running crawl_weibo_society_hot.py ...")
    ret = subprocess.run(
        [sys.executable, "scripts/crawl_weibo_society_hot.py"], cwd=None
    )
    if ret.returncode != 0:
        print("❌ Failed to run crawl_weibo_society_hot.py, aborting.")
        return

    # Step 2: fetch keywords inserted after run_start
    keywords, keyword_to_hot_trend_id = fetch_recent_keywords_with_ids(
        args.mongo, run_start, limit=args.limit
    )
    if not keywords:
        print("⚠️ No keywords found after hot crawl; aborting search.")
        return

    # Step 3: run search crawler
    asyncio.run(run_search(keywords, keyword_to_hot_trend_id))


if __name__ == "__main__":
    main()
