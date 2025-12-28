import os
import requests
import sys
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from datetime import datetime, timezone, timedelta
from typing import List, Any
import argparse
from pathlib import Path
import subprocess

# Ensure project root on sys.path before importing project modules
sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.db_config import MONGO_URI
from tools import utils


def _check_cookie_valid() -> bool:
    """验证当前 .env 下的 WEIBO_COOKIE 是否有效（返回 True/False）。"""
    load_dotenv(override=True)
    cookie = os.getenv("WEIBO_COOKIE", "")
    if not cookie:
        return False
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0 Safari/537.36"
        ),
        "Referer": "https://weibo.com/",
        "Cookie": cookie,
    }
    try:
        r = requests.get(
            "https://weibo.com/ajax/statuses/social", headers=headers, timeout=5
        )
        if r.status_code == 403:
            return False
        return True
    except Exception:
        return False


def hot_search(limit: int | None = None) -> List[Any]:
    """
    仅负责请求并返回原始热搜项列表（不做任何持久化或字段修改）
    limit: 可选，返回前 limit 条
    """
    url = "https://weibo.com/ajax/statuses/social"
    load_dotenv(override=True)
    cookie = os.getenv("WEIBO_COOKIE", "")
    if not cookie:
        print("❌ 未设置 WEIBO_COOKIE 环境变量，无法请求接口")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0 Safari/537.36"
        ),
        "Referer": "https://weibo.com/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 调试输出
        print("接口返回示例：", list(data.keys()))

        if "data" in data and "band_list" in data["data"]:
            items = data["data"]["band_list"]
            return items[:limit] if isinstance(limit, int) and limit > 0 else items

        print("⚠ 接口无 band_list 字段，返回结构可能变更")
        return []

    except requests.exceptions.HTTPError as e:
        if getattr(e.response, "status_code", None) == 403:
            print("❌ 403 Forbidden（通常为未登录或 Cookie 失效）")
            print("👉 建议重新获取浏览器 Cookie，并替换 WEIBO_COOKIE")
        else:
            print(f"HTTP Error: {e}")
        return []

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return []


def main(limit: int = None):
    # 先验证 cookie 是否有效，若无效则自动运行交互式获取脚本刷新 cookie
    if not _check_cookie_valid():
        print("当前 Cookie 缺失或失效，尝试自动刷新（会打开浏览器，请登录后回车）...")
        try:
            fetch_script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "fetch_weibo_cookie.py"
            )
            if fetch_script.exists():
                subprocess.run([sys.executable, str(fetch_script)], check=False)
                # 重新验证
                if not _check_cookie_valid():
                    print("❌ 刷新后 Cookie 仍然无效，停止抓取")
                    return
            else:
                print("fetch_weibo_cookie.py 未找到，请手动运行该脚本获取 Cookie")
                return
        except Exception as e:
            print("自动刷新 Cookie 时出错:", e)
            return

    items = hot_search(limit)
    if not items:
        print("No hot trends fetched.")
        return

    client = MongoClient(MONGO_URI)
    db = client["media_crawler_db"]
    collection = db["hot_trends"]
    coll_hist = db["hot_trends_history"]
    # ensure index on collected_at for efficient time-range queries (idempotent)
    try:
        coll_hist.create_index([("collected_at", -1)])
    except Exception:
        pass

    now = utils.to_china_time_str(utils.get_china_now(), with_tz=True)

    prepared = []
    for idx, item in enumerate(items, 1):
        obj = item.copy() if isinstance(item, dict) else {"value": item}
        # do NOT set collected_at on the hot_trends collection; use last_collected instead
        obj["source"] = "weibo_social"
        obj["rank"] = idx
        prepared.append(obj)

    if prepared:
        ops = []
        for obj in prepared:
            key = {
                "word": obj.get("word") or obj.get("value"),
                "source": obj.get("source"),
            }
            ops.append(
                UpdateOne(
                    key,
                    {
                        "$set": {**obj, "last_collected": now},
                        "$setOnInsert": {"first_collected": now},
                        "$inc": {"seen_count": 1},
                        "$push": {"collected_times": {"$each": [now], "$slice": -50}},
                    },
                    upsert=True,
                )
            )
        if ops:
            res = collection.bulk_write(ops, ordered=False)
            modified = getattr(res, "modified_count", 0)
            upserted = len(getattr(res, "upserted_ids", {}) or {})
            print(f"Upserted hot trends: modified={modified}, upserted={upserted}")
            # 写入本次热搜快照（只保存 word_scheme/word, rank, num(热度) 和时间）
            try:
                snapshot_items = []
                for obj in prepared:
                    word = obj.get("word_scheme") or obj.get("word")
                    rank = obj.get("rank")
                    num = obj.get("num") or None
                    snapshot_items.append({"word": word, "rank": rank, "num": num})
                history_doc = {
                    "collected_at": now,
                    "source": "weibo_social",
                    "top_n": snapshot_items,
                }
                ins = coll_hist.insert_one(history_doc)
                print(f"Inserted hot trends history snapshot: {ins.inserted_id}")
            except Exception as e:
                print(f"Failed to write hot trends history snapshot: {e}")
    else:
        print("No valid items to insert.")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl Weibo society hot search")
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--cookie", type=str, default=None)
    args = parser.parse_args()

    main(args.limit)
