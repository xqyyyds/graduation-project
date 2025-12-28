# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/weibo/__init__.py
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
# @Time    : 2024/1/14 21:34
# @Desc    :

import re
from typing import Dict, List

from var import hot_trend_id_var, source_keyword_var

from .weibo_store_media import *
from ._store_impl import *


class WeibostoreFactory:
    _instances = {}
    STORES = {
        "csv": WeiboCsvStoreImplement,
        "db": WeiboDbStoreImplement,
        "json": WeiboJsonStoreImplement,
        "sqlite": WeiboSqliteStoreImplement,
        "mongodb": WeiboMongoStoreImplement,
        "excel": WeiboExcelStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        save_option = config.SAVE_DATA_OPTION
        if save_option in WeibostoreFactory._instances:
            return WeibostoreFactory._instances[save_option]

        store_class = WeibostoreFactory.STORES.get(save_option)
        if not store_class:
            raise ValueError(
                "[WeibotoreFactory.create_store] Invalid save option only supported csv or db or json or sqlite or mongodb or excel ..."
            )

        instance = store_class()
        WeibostoreFactory._instances[save_option] = instance
        return instance


async def batch_update_weibo_notes(note_list: List[Dict]):
    """
    Batch update weibo notes
    Args:
        note_list:

    Returns:

    """
    if not note_list:
        return
    for note_item in note_list:
        await update_weibo_note(note_item)


async def update_weibo_note(note_item: Dict):
    """
    Update weibo note
    Args:
        note_item:

    Returns:

    """
    if not note_item:
        return

    mblog: Dict = note_item.get("mblog")
    user_info: Dict = mblog.get("user")
    note_id = mblog.get("id")
    content_text = mblog.get("text") or ""
    clean_text = re.sub(r"<.*?>", "", content_text)
    # long text may be present in detailed note (longTextContent / longText)
    full_text = mblog.get("longTextContent") or mblog.get("longText")
    clean_full_text = None
    if full_text:
        clean_full_text = re.sub(r"<.*?>", "", full_text)

    def _normalize_http_url(u: str) -> str:
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http://") or u.startswith("https://"):
            return u
        # 兼容 wx*.sinaimg.cn/... 这种无 scheme 的情况
        if u.startswith("wx") and ".sinaimg.cn/" in u:
            return "https://" + u
        return ""

    # 媒体 URL 复用项目内既有逻辑 + 做最小规范化：
    # - 图片：与 media_platform/weibo/core.py 下载图片一致，取 pic['url']，并补全 https
    # - 视频：从微博返回的结构化字段取出候选，但仅保留可直连的 mp4/m3u8（避免 show/page_H5 等噪音）
    pics = mblog.get("pics") or []
    image_urls: List[str] = []
    for pic in pics:
        if not isinstance(pic, dict):
            continue
        u = pic.get("url")
        if isinstance(u, str) and u:
            nu = _normalize_http_url(u)
            if nu:
                image_urls.append(nu)
    # de-duplicate keep order
    image_urls = list(dict.fromkeys(image_urls))

    # 将图片 URL 转换成 i1.wp.com 代理的大图以保证外部可访问
    def _to_proxy_large_img(u: str) -> str:
        nu = _normalize_http_url(u)
        if not nu:
            return ""
        # remove scheme
        if "://" in nu:
            nu = nu.split("://", 1)[1]
        parts = nu.split("/")
        if len(parts) >= 2:
            # 替换第二段为 large（或插入 large），以获取高清原图
            if len(parts) >= 3:
                parts[1] = "large"
                new_path = "/".join(parts)
            else:
                # 仅域名+文件名的情况，直接插入 large
                new_path = parts[0] + "/large/" + parts[-1]
        else:
            new_path = nu
        return f"https://i1.wp.com/{new_path}"

    page_info = mblog.get("page_info") or {}

    def _extract_video_page_links(page_info: Dict) -> List[str]:
        """从 page_info 中提取 video.weibo.com 的页面链接（保序去重）。"""
        res: List[str] = []
        try:
            s = json.dumps(page_info, ensure_ascii=False)
        except Exception:
            s = ""
        if not s:
            return res
        # 找出所有 http(s) 链接并筛选包含 video.weibo.com 的
        candidates = re.findall(r"https?://[^\s,'\"]+", s)
        for c in candidates:
            if "video.weibo.com" in c and c not in res:
                res.append(c)
        # 另外也检查 page_info 的常见字段保底
        for key in ("page_url", "url", "page_url_original"):
            v = page_info.get(key)
            if isinstance(v, str) and "video.weibo.com" in v and v not in res:
                res.insert(0, v)
        return res

    # 只保留页面链接（video.weibo.com/*），其余直链/噪音均忽略
    video_pages = _extract_video_page_links(page_info)
    video_page_url = video_pages[0] if video_pages else ""

    # 使用代理大图做为可访问的 image_list，同时保留原始链接以便审查
    proxied_images = []
    for u in image_urls:
        pu = _to_proxy_large_img(u)
        if pu:
            proxied_images.append(pu)
    # 去重
    proxied_images = list(dict.fromkeys(proxied_images))

    save_content_item = {
        # 微博信息
        "note_id": note_id,
        "content": clean_text,
        "full_content": clean_full_text or clean_text,
        "create_time": utils.rfc2822_to_timestamp(mblog.get("created_at")),
        "create_date_time": utils.to_china_time_str(
            utils.rfc2822_to_china_datetime(mblog.get("created_at")), with_tz=True
        ),
        "liked_count": str(mblog.get("attitudes_count", 0)),
        "comments_count": str(mblog.get("comments_count", 0)),
        "shared_count": str(mblog.get("reposts_count", 0)),
        "last_modify_ts": utils.get_current_timestamp(),
        "note_url": f"https://m.weibo.cn/detail/{note_id}",
        "ip_location": mblog.get("region_name", "").replace("发布于 ", ""),
        # 媒体信息（无论 ENABLE_GET_MEIDAS 是否开启，都保留 URL）
        "image_list": ",".join(proxied_images) if proxied_images else "",
        "video_url": video_page_url,
        # 用户信息
        "user_id": str(user_info.get("id")),
        "nickname": user_info.get("screen_name", ""),
        "gender": user_info.get("gender", ""),
        "profile_url": user_info.get("profile_url", ""),
        "avatar": user_info.get("profile_image_url", ""),
        "source_keyword": source_keyword_var.get(),
    }

    hot_trend_id = hot_trend_id_var.get()
    if hot_trend_id is not None:
        save_content_item["hot_trend_id"] = hot_trend_id
    utils.logger.info(
        f"[store.weibo.update_weibo_note] weibo note id:{note_id}, title:{save_content_item.get('content')[:24]} ..."
    )
    await WeibostoreFactory.create_store().store_content(content_item=save_content_item)


async def batch_update_weibo_note_comments(note_id: str, comments: List[Dict]):
    """
    Batch update weibo note comments
    Args:
        note_id:
        comments:

    Returns:

    """
    if not comments:
        return
    for comment_item in comments:
        await update_weibo_note_comment(note_id, comment_item)


async def update_weibo_note_comment(note_id: str, comment_item: Dict):
    """
    Update weibo note comment
    Args:
        note_id: weibo note id
        comment_item: weibo comment item

    Returns:

    """
    if not comment_item or not note_id:
        return
    comment_id = str(comment_item.get("id"))
    user_info: Dict = comment_item.get("user")
    content_text = comment_item.get("text")
    clean_text = re.sub(r"<.*?>", "", content_text)
    save_comment_item = {
        "comment_id": comment_id,
        "create_time": utils.rfc2822_to_timestamp(comment_item.get("created_at")),
        "create_date_time": utils.to_china_time_str(
            utils.rfc2822_to_china_datetime(comment_item.get("created_at")),
            with_tz=True,
        ),
        "note_id": note_id,
        "content": clean_text,
        "sub_comment_count": str(comment_item.get("total_number", 0)),
        "comment_like_count": str(comment_item.get("like_count", 0)),
        "last_modify_ts": utils.get_current_timestamp(),
        "ip_location": comment_item.get("source", "").replace("来自", ""),
        "parent_comment_id": comment_item.get("rootid", ""),
        # 用户信息
        "user_id": str(user_info.get("id")),
        "nickname": user_info.get("screen_name", ""),
        "gender": user_info.get("gender", ""),
        "profile_url": user_info.get("profile_url", ""),
        "avatar": user_info.get("profile_image_url", ""),
    }

    hot_trend_id = hot_trend_id_var.get()
    if hot_trend_id is not None:
        save_comment_item["hot_trend_id"] = hot_trend_id
    utils.logger.info(
        f"[store.weibo.update_weibo_note_comment] Weibo note comment: {comment_id}, content: {save_comment_item.get('content', '')[:24]} ..."
    )
    await WeibostoreFactory.create_store().store_comment(comment_item=save_comment_item)


async def update_weibo_note_image(picid: str, pic_content, extension_file_name):
    """
    Save weibo note image to local
    Args:
        picid:
        pic_content:
        extension_file_name:

    Returns:

    """
    await WeiboStoreImage().store_image(
        {
            "pic_id": picid,
            "pic_content": pic_content,
            "extension_file_name": extension_file_name,
        }
    )


async def save_creator(user_id: str, user_info: Dict):
    """
    Save creator information to local
    Args:
        user_id:
        user_info:

    Returns:

    """
    local_db_item = {
        "user_id": user_id,
        "nickname": user_info.get("screen_name"),
        "gender": "女" if user_info.get("gender") == "f" else "男",
        "avatar": user_info.get("avatar_hd"),
        "desc": user_info.get("description"),
        "ip_location": user_info.get("source", "").replace("来自", ""),
        "follows": user_info.get("follow_count", ""),
        "fans": user_info.get("followers_count", ""),
        "tag_list": "",
        "last_modify_ts": utils.get_current_timestamp(),
    }
    utils.logger.info(f"[store.weibo.save_creator] creator:{local_db_item}")
    await WeibostoreFactory.create_store().store_creator(local_db_item)
