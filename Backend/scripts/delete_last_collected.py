#!/usr/bin/env python3
"""删除按 last_collected 日期匹配的文档（支持 YYYY-MM-DD、MM-DD 或 M-D）。默认匹配每年 1 月 5 日（'01-05'）。

说明：项目中的 `last_collected` 字段是字符串，格式如 "YYYY-MM-DD HH:MM:SS"，
脚本会用正则匹配日期部分（例如："2026-01-05"、"01-05" 或 "1-5"）。

用法示例：
  - 预览(默认，不删除): python delete_last_collected.py
  - 预览指定月日:        python delete_last_collected.py 01-05
  - 真正删除:            python delete_last_collected.py 01-05 --execute
  - 指定年:              python delete_last_collected.py 2026-01-05 --execute
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
    print(f"ℹ️ 将 {base} 加入 Python 路径以导入项目包")
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
        "date must be 'YYYY-MM-DD' or 'MM-DD' (e.g. '2026-01-05' or '01-05')"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="按 last_collected 删除指定日期的文档（默认 dry-run）"
    )
    p.add_argument(
        "date",
        nargs="?",
        default="01-05",
        help="要匹配的日期，格式: 'YYYY-MM-DD' 或 'MM-DD'（例如 '2026-01-05' 或 '01-05'）。默认: '01-05'（每年1月5日）",
    )
    p.add_argument(
        "-c",
        "--collections",
        nargs="+",
        default=["hot_trends", "weibo_comments", "weibo_contents"],
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

    try:
        regex = _build_regex_for_date(args.date)
    except ValueError as e:
        print(f"❌ 参数错误: {e}")
        return

    client = MongoClient(args.mongo_uri)
    db = client[args.mongo_db]

    query = {"last_collected": {"$regex": regex}}

    print(f"🔎 将匹配 last_collected 正则: {regex}")

    total_preview = 0
    for coll_name in args.collections:
        coll = db[coll_name]
        try:
            cnt = coll.count_documents(query)
        except Exception as e:
            print(f"⚠️ 读取集合 {coll_name} 时出错: {e}")
            cnt = 0
        print(f" - 集合 `{coll_name}` 匹配到 {cnt} 条文档")
        total_preview += cnt

    if not args.execute:
        print(
            "\n⚠️ 当前为预览模式（dry-run），不会执行删除。若确认删除，请加 --execute 参数并再次运行。"
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
            print(f"✅ 已从 `{coll_name}` 删除 {res.deleted_count} 条文档")
            total_deleted += res.deleted_count
        except Exception as e:
            print(f"❌ 删除 `{coll_name}` 失败: {e}")

    print(f"\n🎯 完成，总共删除 {total_deleted} 条文档。")


if __name__ == "__main__":
    main()
