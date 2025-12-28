#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate simple media crawler reports for a given time window.
"""
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from config.db_config import MONGO_URI
from tools import utils
from tools import utils


def top_trends(start: datetime, end: datetime, limit: int = 30):
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    coll = db["hot_trends"]

    # use ISO+08 string boundaries for comparisons
    start_str = utils.to_china_time_str(start, with_tz=True)
    end_str = utils.to_china_time_str(end, with_tz=True)

    pipeline = [
        {
            "$project": {
                "word": 1,
                "last_collected": 1,
                "hits": {
                    "$size": {
                        "$filter": {
                            "input": "$collected_times",
                            "as": "t",
                            "cond": {
                                "$and": [
                                    {"$gte": ["$$t", start_str]},
                                    {"$lt": ["$$t", end_str]},
                                ]
                            },
                        }
                    }
                },
            }
        },
        {"$match": {"hits": {"$gt": 0}}},
        {"$sort": {"hits": -1, "last_collected": -1}},
        {"$limit": limit},
    ]

    top = list(coll.aggregate(pipeline))
    client.close()
    return top


def report(start: datetime, end: datetime):
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    posts_hist = db["weibo_contents_history"]
    comments_hist = db["weibo_comments_history"]

    start_str = utils.to_china_time_str(start, with_tz=True)
    end_str = utils.to_china_time_str(end, with_tz=True)
    post_events = posts_hist.count_documents(
        {"collected_at": {"$gte": start_str, "$lt": end_str}}
    )
    comment_events = comments_hist.count_documents(
        {"collected_at": {"$gte": start_str, "$lt": end_str}}
    )
    top = top_trends(start, end)

    client.close()

    return {
        "period": (start.isoformat(), end.isoformat()),
        "post_events": post_events,
        "comment_events": comment_events,
        "top_trends": top,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate simple weibo media reports")
    parser.add_argument(
        "--hours", type=int, default=24, help="Lookback window in hours"
    )
    parser.add_argument("--limit", type=int, default=20, help="Top trends to show")
    args = parser.parse_args()

    end = datetime.now(timezone(timedelta(hours=8)))
    start = end - timedelta(hours=args.hours)
    rpt = report(start, end)

    print("Report period:", rpt["period"])
    print("Post events:", rpt["post_events"])
    print("Comment events:", rpt["comment_events"])
    print("Top Trends:")
    for t in rpt["top_trends"]:
        print(
            f" - {t.get('word')} (hits: {t.get('hits')}, last: {t.get('last_collected')})"
        )
