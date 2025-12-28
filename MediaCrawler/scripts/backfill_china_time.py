#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill MongoDB timestamps to China timezone, remove *_human fields,
and add *_cn display fields (ISO string with +08:00).

Usage:
  python scripts/backfill_china_time.py --mongo mongodb://localhost:27017/ --preview

--preview: only show counts, do not modify
"""
from datetime import datetime, timezone

from pymongo import MongoClient
from config.db_config import MONGO_URI
from tools import utils
import argparse

COLLS = ["hot_trends", "hot_trends_history", "weibo_contents", "weibo_comments"]


def convert_to_iso_china(dt):
    """Return ISO+08:00 string for dt, or None."""
    if dt is None:
        return None
    try:
        if isinstance(dt, datetime):
            dt_cn = utils.to_china_datetime(dt)
            return utils.to_china_time_str(dt_cn, with_tz=True)
        if isinstance(dt, (int, float)):
            ts = float(dt)
            if ts >= 1e12:
                ts = ts / 1000.0
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_cn = utils.to_china_datetime(dt_utc)
            return utils.to_china_time_str(dt_cn, with_tz=True)
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt)
                dt_cn = utils.to_china_datetime(parsed)
                return utils.to_china_time_str(dt_cn, with_tz=True)
            except Exception:
                return None
        if isinstance(dt, list):
            out = []
            for x in dt:
                v = convert_to_iso_china(x)
                if v is not None:
                    out.append(v)
            return out
        return None
    except Exception:
        return None


def backfill(mongo_uri: str, do_apply: bool = False):
    client = MongoClient(mongo_uri)
    db = client["media_crawler_db"]

    for coll_name in COLLS:
        coll = db[coll_name]
        total = coll.count_documents({})
        print(f"Processing {coll_name}, docs={total}")

        # Step 1: remove *_human and *_cn fields
        removal_fields = set()
        sample = coll.find_one()
        if sample:
            for k in sample.keys():
                if k.endswith("_human") or k.endswith("_cn"):
                    removal_fields.add(k)
        if removal_fields:
            print(
                f" - Will unset *_human/_cn fields (best-effort): {sorted(removal_fields)}"
            )
            if do_apply:
                res = coll.update_many(
                    {}, {"$unset": {k: "" for k in sorted(removal_fields)}}
                )
                print(f"   Unset fields, modified: {getattr(res, 'modified_count', 0)}")
            else:
                print("   Preview only (no changes)")

        # Special: for hot_trends, remove collected_at field (we use last_collected instead)
        if coll_name == "hot_trends":
            q_col = {"collected_at": {"$exists": True}}
            cnt_col = coll.count_documents(q_col)
            if cnt_col > 0:
                print(f" - hot_trends: will unset collected_at in {cnt_col} docs")
                if do_apply:
                    res = coll.update_many({}, {"$unset": {"collected_at": ""}})
                    print(
                        f"   Unset collected_at, modified: {getattr(res, 'modified_count', 0)}"
                    )
                else:
                    print("   Preview only (no changes)")

        # Step 2: convert first_collected/last_collected/collected_at (and collected_times lists) to ISO+08 strings
        for field in (
            "first_collected",
            "last_collected",
            "collected_at",
            "collected_times",
        ):
            q = {field: {"$exists": True}}
            count = coll.count_documents(q)
            if count == 0:
                continue
            print(f" - Field {field} present in {count} docs")
            if do_apply:
                cursor = coll.find(q, {"_id": 1, field: 1})
                modified = 0
                for doc in cursor:
                    old = doc.get(field)
                    # list fields (collected_times) -> convert each element
                    if isinstance(old, list):
                        new_list = convert_to_iso_china(old)
                        if new_list and new_list != old:
                            coll.update_one(
                                {"_id": doc["_id"]}, {"$set": {field: new_list}}
                            )
                            modified += 1
                        continue
                    new_iso = convert_to_iso_china(old)
                    if new_iso is None:
                        continue
                    if new_iso != old:
                        coll.update_one({"_id": doc["_id"]}, {"$set": {field: new_iso}})
                        modified += 1
                print(f"   Converted {modified} documents for field {field}")
            else:
                print("   Preview only (no changes)")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill Mongo timestamps to China timezone and remove *_human fields"
    )
    parser.add_argument("--mongo", type=str, default=MONGO_URI, help="MongoDB URI")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (default is preview)"
    )
    args = parser.parse_args()

    backfill(args.mongo, do_apply=args.apply)
