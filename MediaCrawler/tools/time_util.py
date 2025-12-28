# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/time_util.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/2 12:52
# @Desc    : 时间相关的工具函数

import time
from datetime import datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8))


def get_china_now() -> datetime:
    """Return timezone-aware current datetime in China (UTC+8)."""
    return datetime.now(CHINA_TZ)


def to_china_datetime(dt: datetime) -> datetime:
    """Convert a datetime to China timezone (UTC+8)."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        # Treat naive datetime as local time, then attach China tz.
        return dt.replace(tzinfo=CHINA_TZ)
    return dt.astimezone(CHINA_TZ)


def to_china_time_str(dt: datetime, with_tz: bool = True) -> str:
    """Format datetime in China timezone for display.

    Format used for storage/display: "YYYY-MM-DD HH:MM:SS+08:00" when with_tz=True.
    """
    dt_cn = to_china_datetime(dt)
    if dt_cn is None:
        return ""
    if not with_tz:
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    # produce offset like +08:00 (with colon)
    base = dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    tz_no_colon = dt_cn.strftime("%z")  # e.g. +0800
    tz = tz_no_colon[:3] + ":" + tz_no_colon[3:]
    return f"{base}{tz}"


def get_current_timestamp() -> int:
    """
    获取当前的时间戳(13 位)：1701493264496
    :return:
    """
    return int(time.time() * 1000)


def get_current_time() -> str:
    """
    获取当前的时间：'2023-12-02 13:01:23'
    :return:
    """
    return time.strftime("%Y-%m-%d %X", time.localtime())


def get_current_time_hour() -> str:
    """
    获取当前的时间：'2023-12-02-13'
    :return:
    """
    return time.strftime("%Y-%m-%d-%H", time.localtime())


def get_current_date() -> str:
    """
    获取当前的日期：'2023-12-02'
    :return:
    """
    return time.strftime("%Y-%m-%d", time.localtime())


def get_time_str_from_unix_time(unixtime):
    """
    unix 整数类型时间戳  ==> 字符串日期时间
    :param unixtime:
    :return:
    """
    if int(unixtime) > 1000000000000:
        unixtime = int(unixtime) / 1000
    return time.strftime("%Y-%m-%d %X", time.localtime(unixtime))


def get_date_str_from_unix_time(unixtime):
    """
    unix 整数类型时间戳  ==> 字符串日期
    :param unixtime:
    :return:
    """
    if int(unixtime) > 1000000000000:
        unixtime = int(unixtime) / 1000
    return time.strftime("%Y-%m-%d", time.localtime(unixtime))


def get_unix_time_from_time_str(time_str):
    """
    字符串时间 ==> unix 整数类型时间戳，精确到秒
    :param time_str:
    :return:
    """
    try:
        format_str = "%Y-%m-%d %H:%M:%S"
        tm_object = time.strptime(str(time_str), format_str)
        return int(time.mktime(tm_object))
    except Exception as e:
        return 0
    pass


def get_unix_timestamp():
    return int(time.time())


def rfc2822_to_china_datetime(rfc2822_time):
    # 定义RFC 2822格式
    rfc2822_format = "%a %b %d %H:%M:%S %z %Y"

    # 将RFC 2822时间字符串转换为datetime对象
    dt_object = datetime.strptime(rfc2822_time, rfc2822_format)

    # 将datetime对象的时区转换为中国时区
    dt_object_china = dt_object.astimezone(CHINA_TZ)
    return dt_object_china


def rfc2822_to_timestamp(rfc2822_time):
    # 定义RFC 2822格式
    rfc2822_format = "%a %b %d %H:%M:%S %z %Y"

    # 将RFC 2822时间字符串转换为datetime对象
    dt_object = datetime.strptime(rfc2822_time, rfc2822_format)

    # 转为 UTC 再取时间戳（时间戳本身与时区无关）
    dt_utc = dt_object.astimezone(timezone.utc)

    # 计算UTC时间对应的Unix时间戳
    timestamp = int(dt_utc.timestamp())

    return timestamp


if __name__ == "__main__":
    # 示例用法
    _rfc2822_time = "Sat Dec 23 17:12:54 +0800 2023"
    print(rfc2822_to_china_datetime(_rfc2822_time))
