"""Export Top20 hot search words per category.

Usage:
    python export_top20_by_category.py --start 2026-01-15 --end 2026-01-16

This script aggregates hot search snapshots in the given date range and computes
Top-20 words for each category in CATEGORIES. Results are saved into MongoDB
collection `hot_top_by_category` and exported as JSON into `output/`.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict

# Ensure project root (Backend) is on sys.path so `import app` works
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from app.db.mongo_manager import MongoManager
    from app.core.logger import logger
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(
        "无法导入 'app' 包。请确保从项目的 'Backend' 目录运行脚本或将项目根目录加入 PYTHONPATH。"
        f" 原始错误: {e}"
    )

# Categories to export
CATEGORIES = ["综合", "社会", "高校", "生活", "科技", "政治"]


def _validate_date(d: str) -> str:
    if not d:
        return d
    d = d.strip()
    # Accept YYYY-MM-DD
    import re

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        raise ValueError("日期格式错误，应为 YYYY-MM-DD")
    return d


def aggregate_top_by_category(
    items: List[Dict], top_n: int = 40
) -> Dict[str, List[Dict]]:
    """Aggregate items (list of {word,num,category}) into top lists per category."""
    from collections import defaultdict

    aggr = {}

    # initialize counters
    counters = defaultdict(lambda: {})

    for it in items:
        word = (it.get("word") or "").strip()
        if not word:
            continue
        cat = it.get("category") or "未知"
        try:
            num = int(it.get("num") or 1)
        except Exception:
            num = 1

        counters[cat][word] = counters[cat].get(word, 0) + num

    for cat in CATEGORIES:
        word_map = counters.get(cat, {})
        sorted_words = sorted(word_map.items(), key=lambda x: (-x[1], x[0]))
        aggr[cat] = [{"word": w, "score": s} for w, s in sorted_words[:top_n]]

    return aggr


def main(
    start_date: str,
    end_date: str,
    top_n: int = 40,
    save_to_db: bool = True,
    output_dir: str = "output",
):
    mm = MongoManager()

    # Ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f" 正在从 {start_date} 到 {end_date} 聚合热搜数据...")
    items = mm.get_raw_trend_items(start_date, end_date)

    if not items:
        logger.warning(" 未检索到任何热搜数据，检查日期范围或数据采集状态。")
        return

    aggr = aggregate_top_by_category(items, top_n=top_n)

    now = datetime.now().isoformat(sep=" ")
    payload = {
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": now,
        "top_n": top_n,
        "results": aggr,
    }

    # Save to MongoDB collection 'hot_top_by_category'
    if save_to_db:
        doc = dict(payload)
        # Add human-friendly summary counts
        doc["summary_counts"] = {k: len(v) for k, v in aggr.items()}
        mm.get_collection("hot_top_by_category").insert_one(doc)
        logger.info(" 已将聚合结果写入集合 'hot_top_by_category'。")

    # Save JSON file
    out_file = os.path.join(
        output_dir, f"top40_by_category_{start_date}_to_{end_date}.json"
    )
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f" 已导出 JSON 文件: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Top40 hot search words per category to DB and JSON."
    )
    parser.add_argument("--start", type=str, help="开始日期 YYYY-MM-DD", required=True)
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD", required=True)
    parser.add_argument("--top", type=int, help="每类 TopN，大于0", default=40)
    parser.add_argument(
        "--no-db", action="store_true", help="不写入 MongoDB，仅导出 JSON"
    )
    parser.add_argument("--output", type=str, help="导出目录", default="output")

    args = parser.parse_args()

    try:
        s = _validate_date(args.start)
        e = _validate_date(args.end)
    except Exception as exc:
        print(f" 参数错误: {exc}")
        raise SystemExit(1)

    main(
        start_date=s,
        end_date=e,
        top_n=args.top,
        save_to_db=not args.no_db,
        output_dir=args.output,
    )
