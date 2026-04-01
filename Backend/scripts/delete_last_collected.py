#!/usr/bin/env python3
"""删除按 last_collected 日期匹配的文档（支持 YYYY-MM-DD、MM-DD 或 M-D）。

默认行为：若不传参数，脚本将默认删除 2026-01-05 14:00 之后的文档（可传入其他阈值）。

说明：项目中的 `last_collected` 字段是字符串，格式如 "YYYY-MM-DD HH:MM:SS"，
脚本会用正则匹配日期部分（例如："2026-01-05"、"01-05" 或 "1-5"），或接受带时分的阈值（例如 "2026-01-05 14:00"）。

用法示例：
  - 预览(默认，不删除): python delete_last_collected.py
  - 预览指定月日:        python delete_last_collected.py 01-05
  - 真正删除:            python delete_last_collected.py 01-05 --execute
  - 指定年:              python delete_last_collected.py 2026-01-05 --execute
  - 按时间阈值删除:      python delete_last_collected.py "2026-01-05 14:00" --execute
  - 指定集合:            python delete_last_collected.py 01-05 -c weibo_contents weibo_comments --execute
"""

from __future__ import annotations

import re
import argparse
import sys
from typing import List
from pymongo import MongoClient

# 尝试导入项目设置，若失败则把上级目录（项目的 Backend 目录）加入 sys.path 以兼容直接从脚本文件夹运行的情况
try:
    from app.core.config import settings
except ModuleNotFoundError:
    from pathlib import Path

    base = Path(__file__).resolve().parents[1]  # 指向 Backend/ 目录
    sys.path.insert(0, str(base))
    print(f"INFO: 将 {base} 加入 Python 路径以导入项目包")
    from app.core.config import settings


def _build_regex_for_date(date_str: str) -> str:
    """支持 'YYYY-MM-DD' 或 'MM-DD'（或 'M-D'）两种输入，返回用于匹配 `last_collected` 的正则字符串。

    会把单数月/日补零，例如 '1-5' -> '01-05'，以便正确匹配数据库中 'YYYY-MM-DD HH:MM:SS' 格式的字符串。
    """
    date_str = date_str.strip()
    # 匹配 YYYY-M-D 或 YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if m:
        y, mm, dd = m.groups()
        mm = mm.zfill(2)
        dd = dd.zfill(2)
        return f"^{y}-{mm}-{dd}"

    # 匹配 M-D 或 MM-DD
    m2 = re.match(r"^(\d{1,2})-(\d{1,2})$", date_str)
    if m2:
        mm, dd = m2.groups()
        mm = mm.zfill(2)
        dd = dd.zfill(2)
        return rf"^\d{{4}}-{mm}-{dd}"

    raise ValueError(
        "date must be 'YYYY-MM-DD' or 'MM-DD' (e.g. '2026-01-05' or '01-05').\n"
        "To delete documents after a specific datetime, pass 'YYYY-MM-DD HH:MM' (e.g. '2026-01-05 14:00')."
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="按 last_collected 删除指定日期或时间之后的文档（默认 dry-run）"
    )
    p.add_argument(
        "--date",
        nargs="?",
        default="2026-01-17 14:00",
        help=(
            "要匹配的日期，格式: 'YYYY-MM-DD' 或 'MM-DD'（例如 '2026-01-05' 或 '01-05'）。默认: '2026-01-17 14:00'（删除该时间点之后的文档）。\n"
            "若需按整日/月日匹配，可传 'YYYY-MM-DD' 或 'MM-DD'（例如 '01-05'）。"
        ),
    )
    p.add_argument(
        "-c",
        "--collections",
        nargs="+",
        default=["hot_trends", "weibo_comments", "weibo_contents","hot_trends_history"],
        help="要处理的集合，默认: hot_trends weibo_comments weibo_contents",
    )
    p.add_argument(
        "-x", "--execute", action="store_true", help="实际执行删除（否则仅做预览）"
    )
    p.add_argument(
        "--mongo-uri",
        default=settings.MONGO_URI,
        help="MongoDB URI（默认使用项目配置）",
    )
    p.add_argument(
        "--mongo-db",
        default=settings.MONGO_DB_NAME,
        help="数据库名（默认使用项目配置）",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    client = MongoClient(args.mongo_uri)
    db = client[args.mongo_db]

    # 如果 date 参数里包含时间 (HH:MM)，我们把它视为“删除该时间点之后”的阈值
    dt_with_time = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})(:\d{2})?$", args.date
    )

    # 若未传时间（或传的是 MM-DD/ YYYY-MM-DD），构建正则用于匹配日期或月日
    regex = None
    if not dt_with_time:
        try:
            regex = _build_regex_for_date(args.date)
        except ValueError as e:
            print(f" 参数错误: {e}")
            return

    total_preview = 0

    if dt_with_time:
        # 构建阈值 datetime（含时区 +08:00），并用 $expr + $dateFromString 做比较
        date_part = dt_with_time.group(1)
        hm = dt_with_time.group(2)
        ss = dt_with_time.group(3) or ":00"
        threshold_str = f"{date_part} {hm}{ss}+08:00"  # 与 DB 格式对齐
        # 将阈值解析为 Python datetime（BSON Date）
        from datetime import datetime as _dt, timezone, timedelta as _td

        tz_cn = timezone(_td(hours=8))
        fmt = "%Y-%m-%d %H:%M:%S%z"
        try:
            threshold_dt = _dt.strptime(threshold_str, fmt)
        except Exception:
            print(f" 无法解析时间阈值: {threshold_str}")
            return

        print(f"INFO: 将删除 last_collected > {threshold_str} 的文档 (使用日期解析比较)")

        # Mongo 查询使用 $expr + $dateFromString：解析文档字段并与阈值比较
        query = {
            "$expr": {
                "$gt": [
                    {"$dateFromString": {"dateString": "$last_collected"}},
                    threshold_dt,
                ]
            }
        }

        for coll_name in args.collections:
            coll = db[coll_name]
            try:
                cnt = coll.count_documents(query)
            except Exception as e:
                print(f" 读取集合 {coll_name} 时出错: {e}")
                cnt = 0
            print(
                f" - 集合 `{coll_name}` 匹配到 {cnt} 条文档 (last_collected > {threshold_str})"
            )
            total_preview += cnt

    else:
        # 原有日期/月份匹配逻辑
        query = {"last_collected": {"$regex": regex}}

        print(f"INFO: 将匹配 last_collected 正则: {regex}")

        for coll_name in args.collections:
            coll = db[coll_name]
            try:
                cnt = coll.count_documents(query)
            except Exception as e:
                print(f" 读取集合 {coll_name} 时出错: {e}")
                cnt = 0
            print(f" - 集合 `{coll_name}` 匹配到 {cnt} 条文档")
            total_preview += cnt

    if not args.execute:
        print(
            "\n 当前为预览模式（dry-run），不会执行删除。若确认删除，请加 --execute 参数并再次运行。"
        )
        return

    # 二次确认
    confirm = input("确定要删除以上列出数量的所有文档吗？输入 'yes' 确认: ")
    if confirm.strip().lower() != "yes":
        print("已取消。")
        return

    # 执行删除
    total_deleted = 0
    for coll_name in args.collections:
        coll = db[coll_name]
        try:
            res = coll.delete_many(query)
            print(f" 已从 `{coll_name}` 删除 {res.deleted_count} 条文档")
            total_deleted += res.deleted_count
        except Exception as e:
            print(f" 删除 `{coll_name}` 失败: {e}")

    print(f"\n 完成，总共删除 {total_deleted} 条文档。")

    # 小提醒：若你使用的是带时间阈值模式，删除条件使用了 MongoDB 的 $dateFromString，确保你的 MongoDB 版本支持该表达式（MongoDB 4.0+ 一般支持）。
    if dt_with_time:
        print(
            " 注意：时间阈值比较使用了 Mongo 的 $dateFromString 解析，如果数据库字段中存在不规范的时间字符串，可能会被忽略。"
        )


if __name__ == "__main__":
    main()
