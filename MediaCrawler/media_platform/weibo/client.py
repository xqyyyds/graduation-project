# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/weibo/client.py
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
# @Time    : 2023/12/23 15:40
# @Desc    : 微博爬虫 API 请求 client

import asyncio
import copy
import json
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union
import random
from urllib.parse import parse_qs, unquote, urlencode
import time
from collections import defaultdict

import httpx
from httpx import Response
from playwright.async_api import BrowserContext, Page
from tenacity import retry, stop_after_attempt, wait_fixed

import config
from proxy.proxy_mixin import ProxyRefreshMixin
from tools import utils

if TYPE_CHECKING:
    from proxy.proxy_ip_pool import ProxyIpPool

from .exception import DataFetchError
from .field import SearchType


# ====== IPv6池轮询配置（如需全局开关可移到 config/var.py） ======
ENABLE_IPV6_POOL = True  # 如需关闭，设为False
MY_IPV6_PREFIX = "2001:250:4000:5113"
MY_IPV6_POOL = [f"{MY_IPV6_PREFIX}::{i:x}" for i in range(1, 0x15)]  # ::1 ~ ::14
# =========================================================


class WeiboClient(ProxyRefreshMixin):

    def _ipv6_pool_enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_IPV6_POOL", ENABLE_IPV6_POOL))

    def _get_ipv6_pool(self) -> List[str]:
        pool = getattr(config, "IPV6_POOL", None)
        if isinstance(pool, list) and pool:
            return pool
        return MY_IPV6_POOL

    def _pick_ipv6(self) -> Optional[str]:
        pool = self._get_ipv6_pool()
        now = time.time()
        candidates = [
            ip
            for ip in pool
            if self._ipv6_state[ip]["bad_until"] <= now
            and self._ipv6_state[ip]["inflight"] < self._per_ip_concurrency
        ]
        if candidates:
            # simple random selection from the whole healthy candidate pool
            return random.choice(candidates)

        # 没有健康 candidate：尝试选择最早到期的 IP 做探测以避免全部被拉黑
        pool_sorted = sorted(pool, key=lambda ip: self._ipv6_state[ip]["bad_until"])
        if not pool_sorted:
            return None
        earliest = pool_sorted[0]
        # 如果它的冷却快要到期（提前窗口），允许探测；或者所有 ip 都在冷却时允许探测
        soon = self._ipv6_state[earliest]["bad_until"] - now <= self._ip_probe_ahead
        all_bad = all(self._ipv6_state[ip]["bad_until"] > now for ip in pool)
        if (soon or all_bad) and self._ipv6_state[earliest][
            "inflight"
        ] < self._per_ip_concurrency:
            utils.logger.info(
                f"[IPv6轮询] 无健康出口，选择 {earliest} 进行探测（可能仍在冷却）"
            )
            return earliest
        return None

    def _build_httpx_client(self) -> httpx.AsyncClient:
        """Build an AsyncClient using IPv6 local_address rotation when enabled.

        Uses _pick_ipv6 for smarter selection and marks per-IP inflight counters.
        Falls back to default connection when local binding fails.
        """
        if self._ipv6_pool_enabled():
            source_ip = self._pick_ipv6()
            if source_ip is None:
                # no healthy ip, fallback to default client
                utils.logger.warning(
                    "[IPv6轮询] no healthy IPv6 candidate, using default connection"
                )
                return httpx.AsyncClient()
            try:
                # increment inflight immediately; will decrement in request() finally
                self._ipv6_state[source_ip]["inflight"] += 1
                transport = httpx.AsyncHTTPTransport(local_address=source_ip, retries=1)
                client = httpx.AsyncClient(transport=transport)
                # attach metadata so request() can access it
                setattr(client, "_mc_source_ip", source_ip)
                utils.logger.info(f"[IPv6轮询] 当前出口IP: {source_ip}")
                return client
            except Exception as e:
                utils.logger.warning(
                    f"[IPv6轮询] 绑定 {source_ip} 失败，降级默认连接: {e}"
                )
                # do not mark ip as bad; just fallback to default connection
                return httpx.AsyncClient()
        return httpx.AsyncClient(proxy=self.proxy)

    def __init__(
        self,
        timeout=60,  # 若开启爬取媒体选项，weibo 的图片需要更久的超时时间
        proxy=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self._host = "https://m.weibo.cn"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._image_agent_host = "https://i1.wp.com/"
        # 初始化代理池（来自 ProxyRefreshMixin）
        self.init_proxy_pool(proxy_ip_pool)

        # IPv6 状态： per-ip inflight, fails, bad_until
        self._ipv6_state = defaultdict(
            lambda: {"inflight": 0, "fails": 0, "bad_until": 0.0}
        )
        self._per_ip_concurrency = getattr(config, "IPV6_PER_IP_CONCURRENCY", 1)

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(3))
    async def request(self, method, url, **kwargs) -> Union[Response, Dict]:
        # 每次请求前检测代理是否过期（如未启用IPv6池，才刷新代理）
        if not self._ipv6_pool_enabled():
            await self._refresh_proxy_if_expired()

        enable_return_response = kwargs.pop("return_response", False)

        # 默认携带 headers（包含 Cookie），避免部分调用直接 request() 时丢失登录态导致 302 跳转 visitor
        if kwargs.get("headers") is None:
            kwargs["headers"] = self.headers

        # 支持单次请求传入 timeout 覆盖
        request_timeout = kwargs.pop(
            "timeout", getattr(config, "WEIBO_REQUEST_TIMEOUT_SEC", self.timeout)
        )
        total_timeout = getattr(
            config, "WEIBO_REQUEST_TOTAL_TIMEOUT_SEC", request_timeout + 5
        )

        client = self._build_httpx_client()
        source_ip = getattr(client, "_mc_source_ip", None)
        try:
            async with client as c:
                # 把单次请求包装在一个总体超时内，避免协程被长时间挂住
                response = await asyncio.wait_for(
                    c.request(method, url, timeout=request_timeout, **kwargs),
                    timeout=total_timeout,
                )
        except (OSError, httpx.RequestError, asyncio.TimeoutError) as e:
            # 不再标记 IP 为 bad；仅记录并马上回退到直连
            utils.logger.warning(
                f"[WeiboClient.request] connect failed ({type(e).__name__}), fallback once: {e}"
            )
            try:
                async with httpx.AsyncClient(proxy=None) as c:
                    response = await asyncio.wait_for(
                        c.request(method, url, timeout=request_timeout, **kwargs),
                        timeout=total_timeout,
                    )
            except (OSError, httpx.RequestError, asyncio.TimeoutError) as e2:
                utils.logger.error(
                    f"[WeiboClient.request] fallback failed ({type(e2).__name__}): {e2}"
                )
                # 抛出异常以触发重试并保留具体错误信息（不要返回空的 599 响应或空 dict）
                raise DataFetchError(f"fallback failed ({type(e2).__name__}): {e2}")
        finally:
            # 如果用了某个 ipv6，请确保减少 inflight 计数
            if source_ip:
                # already decremented, ensure it cannot go negative
                self._ipv6_state[source_ip]["inflight"] = max(
                    0, self._ipv6_state[source_ip]["inflight"] - 1
                )

        # 返回原始 Response（用于需要原始 response 的调用，如 get_note_info_by_id）
        if enable_return_response:
            return response

        try:
            data: Dict = response.json()
        except json.decoder.JSONDecodeError:
            # issue: #771 搜索接口会报错432， 多次重试 + 更新 h5 cookies
            utils.logger.error(
                f"[WeiboClient.request] request {method}:{url} err code: {getattr(response, 'status_code', 'N/A')} res:{getattr(response, 'text', '')}"
            )
            await self.playwright_page.goto(self._host)
            await asyncio.sleep(2)
            await self.update_cookies(browser_context=self.playwright_page.context)
            raise DataFetchError(
                f"get response code error: {getattr(response, 'status_code', 'N/A')}"
            )

        # 检查接口返回的 ok 字段来判断是否存在实际数据或错误
        ok_code = data.get("ok")
        # 特殊处理：没有评论或空结果，不重试，直接返回空或原始响应供上层判断
        if ok_code == 0:
            msg = data.get("msg", "") or ""
            # 常见的“无评论/无内容”提示直接返回原始响应，交给上层决定如何处理
            if (
                msg.startswith("还没有人评论")
                or msg.startswith("快来发表你的评论吧")
                or "这里还没有内容" in msg
            ):
                utils.logger.info(
                    f"[WeiboClient.request] no content for url:{url}, msg:{msg}"
                )
                return data
            # 特殊情况：data 中明确返回了空 cards，也当作无内容返回
            if isinstance(data.get("data"), dict) and data["data"].get("cards") == []:
                utils.logger.info(
                    f"[WeiboClient.request] empty cards for url:{url}, treat as no content"
                )
                return data
            # 其它 ok:0 情况视为异常（如被限流、被阻止），继续抛出以触发重试/退避机制
            req_headers = kwargs.get("headers") or {}
            utils.logger.error(
                "[WeiboClient.request] request %s:%s err, status:%s location:%s has_cookie:%s referer:%s source_ip:%s res:%s",
                method,
                url,
                getattr(response, "status_code", "N/A"),
                getattr(response, "headers", {}).get("Location", ""),
                bool(req_headers.get("Cookie")),
                req_headers.get("Referer", ""),
                source_ip or "",
                data,
            )
            raise DataFetchError(
                f"request {method}:{url} err, msg:{data.get('msg','')}, status:{getattr(response, 'status_code', 'N/A')}, data_snippet:{json.dumps(data)[:200]}"
            )
        elif ok_code != 1:  # unknown error
            req_headers = kwargs.get("headers") or {}
            utils.logger.error(
                "[WeiboClient.request] request %s:%s err, status:%s location:%s has_cookie:%s referer:%s source_ip:%s res:%s",
                method,
                url,
                getattr(response, "status_code", "N/A"),
                getattr(response, "headers", {}).get("Location", ""),
                bool(req_headers.get("Cookie")),
                req_headers.get("Referer", ""),
                source_ip or "",
                data,
            )
            raise DataFetchError(
                f"request {method}:{url} err, msg:{data.get('msg','')}, status:{getattr(response, 'status_code', 'N/A')}, data_snippet:{json.dumps(data)[:200]}"
            )
        else:  # response right
            # 成功时把 source ip 标记为成功，重置失败计数
            if source_ip:
                self._mark_ipv6_success(source_ip)
            return data.get("data", {})

    def _mark_ipv6_bad(self, ip: Optional[str], reason: str):
        # Kept for backward compatibility but no longer actively used in the path
        if not ip:
            return
        s = self._ipv6_state[ip]
        s["fails"] += 1
        s["last_fail_ts"] = time.time()
        # reduce inflight if necessary
        s["inflight"] = max(0, s["inflight"] - 1)
        utils.logger.info(f"[IPv6轮询] {ip} 记录失败 (不立即拉黑): {reason}")

    def _mark_ipv6_success(self, ip: Optional[str]):
        if not ip:
            return
        s = self._ipv6_state[ip]
        s["consecutive_fails"] = 0
        s["fails"] = 0
        s["last_success_ts"] = time.time()
        s["bad_until"] = 0.0
        utils.logger.debug(f"[IPv6轮询] {ip} 恢复为健康状态 (成功回应)")
        # end of _mark_ipv6_success

    async def get(
        self, uri: str, params=None, headers=None, **kwargs
    ) -> Union[Response, Dict]:
        final_uri = uri
        if isinstance(params, dict):
            final_uri = f"{uri}?" f"{urlencode(params)}"

        if headers is None:
            headers = self.headers
        return await self.request(
            method="GET", url=f"{self._host}{final_uri}", headers=headers, **kwargs
        )

    async def post(self, uri: str, data: dict) -> Dict:
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self.request(
            method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers
        )

    async def pong(self) -> bool:
        """get a note to check if login state is ok"""
        utils.logger.info("[WeiboClient.pong] Begin pong weibo...")
        ping_flag = False
        try:
            uri = "/api/config"
            resp_data: Dict = await self.request(
                method="GET", url=f"{self._host}{uri}", headers=self.headers
            )
            if resp_data.get("login"):
                ping_flag = True
            else:
                utils.logger.error(
                    f"[WeiboClient.pong] cookie may be invalid and again login..."
                )
        except Exception as e:
            utils.logger.error(
                f"[WeiboClient.pong] Pong weibo failed: {e}, and try to login again..."
            )
            ping_flag = False
        return ping_flag

    async def update_cookies(
        self, browser_context: BrowserContext, urls: Optional[List[str]] = None
    ):
        """
        Update cookies from browser context
        :param browser_context: Browser context
        :param urls: Optional list of URLs to filter cookies (e.g., ["https://m.weibo.cn"])
                     If provided, only cookies for these URLs will be retrieved
        """
        if urls:
            cookies = await browser_context.cookies(urls=urls)
            utils.logger.info(
                f"[WeiboClient.update_cookies] Updating cookies for specific URLs: {urls}"
            )
        else:
            cookies = await browser_context.cookies()
            utils.logger.info("[WeiboClient.update_cookies] Updating all cookies")

        cookie_str, cookie_dict = utils.convert_cookies(cookies)
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict
        utils.logger.info(
            f"[WeiboClient.update_cookies] Cookie updated successfully, total: {len(cookie_dict)} cookies"
        )

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        search_type: SearchType = SearchType.DEFAULT,
    ) -> Dict:
        """
        search note by keyword
        :param keyword: 微博搜搜的关键词
        :param page: 分页参数 -当前页码
        :param search_type: 搜索的类型，见 weibo/filed.py 中的枚举SearchType
        :return:
        """
        uri = "/api/container/getIndex"
        containerid = f"100103type={search_type.value}&q={keyword}"
        params = {
            "containerid": containerid,
            "page_type": "searchall",
            "page": page,
        }
        return await self.get(uri, params)

    async def get_note_comments(
        self, mid_id: str, max_id: int, max_id_type: int = 0
    ) -> Dict:
        """get notes comments
        :param mid_id: 微博ID
        :param max_id: 分页参数ID
        :param max_id_type: 分页参数ID类型
        :return:
        """
        uri = "/comments/hotflow"
        params = {
            "id": mid_id,
            "mid": mid_id,
            "max_id_type": max_id_type,
        }
        if max_id > 0:
            params.update({"max_id": max_id})
        referer_url = f"https://m.weibo.cn/detail/{mid_id}"
        headers = copy.copy(self.headers)
        headers["Referer"] = referer_url

        return await self.get(uri, params, headers=headers)

    async def get_note_all_comments(
        self,
        note_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ):
        """
        get note all comments include sub comments
        :param note_id:
        :param crawl_interval:
        :param callback:
        :param max_count:
        :return:
        """
        result = []
        is_end = False
        max_id = -1
        max_id_type = 0
        while not is_end and len(result) < max_count:
            comments_res = await self.get_note_comments(note_id, max_id, max_id_type)
            if not isinstance(comments_res, dict) or not comments_res:
                break
            # If response indicates no content / no comments, stop
            if isinstance(comments_res, dict) and comments_res.get("ok") == 0:
                msg = comments_res.get("msg", "") or ""
                if msg.startswith("还没有人评论") or msg.startswith(
                    "快来发表你的评论吧"
                ):
                    return []
            max_id = int(comments_res.get("max_id") or 0)
            max_id_type = int(comments_res.get("max_id_type") or 0)
            comment_list: List[Dict] = comments_res.get("data", [])
            is_end = max_id == 0
            if len(result) + len(comment_list) > max_count:
                comment_list = comment_list[: max_count - len(result)]
            if callback:  # 如果有回调函数，就执行回调函数
                await callback(note_id, comment_list)
            result.extend(comment_list)
            if not is_end and len(result) < max_count:
                await asyncio.sleep(crawl_interval)
            sub_comment_result = await self.get_comments_all_sub_comments(
                note_id, comment_list, callback
            )
            result.extend(sub_comment_result)
        return result

    @staticmethod
    async def get_comments_all_sub_comments(
        note_id: str,
        comment_list: List[Dict],
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取评论的所有子评论
        Args:
            note_id:
            comment_list:
            callback:

        Returns:

        """
        if not config.ENABLE_GET_SUB_COMMENTS:
            return []

        res_sub_comments = []
        for comment in comment_list:
            sub_comments = comment.get("comments")
            if sub_comments and isinstance(sub_comments, list):
                await callback(note_id, sub_comments)
                res_sub_comments.extend(sub_comments)
        return res_sub_comments

    async def get_note_info_by_id(self, note_id: str) -> Dict:
        """
        根据帖子ID获取详情
        :param note_id:
        :return:
        """
        url = f"{self._host}/detail/{note_id}"
        # reuse request wrapper to get raw response (with timeout/fallback)
        response = await self.request(
            "GET", url, headers=self.headers, return_response=True
        )
        # 明确处理非 Response 或非 200 情况，给出更有用的错误信息以便定位
        if not isinstance(response, Response):
            raise DataFetchError(
                "get weibo detail err: no response (fallback returned empty)"
            )
        if response.status_code != 200:
            body = getattr(response, "text", "") or ""
            location = response.headers.get("Location", "")
            # 如果是重定向（常见于登录/被拦截），尝试用 Playwright 刷新 cookies 并重试一次
            if 300 <= response.status_code < 400:
                utils.logger.warning(
                    f"[WeiboClient.get_note_info_by_id] got redirect status={response.status_code} location={location}, refreshing cookies and retrying once"
                )
                try:
                    await self.playwright_page.goto(self._host)
                    await asyncio.sleep(2)
                    await self.update_cookies(
                        browser_context=self.playwright_page.context
                    )
                except Exception as e:
                    utils.logger.debug(
                        "[WeiboClient.get_note_info_by_id] failed to refresh cookies via playwright",
                        exc_info=True,
                    )
                # retry once
                response2 = await self.request(
                    "GET", url, headers=self.headers, return_response=True
                )
                if isinstance(response2, Response) and response2.status_code == 200:
                    response = response2
                else:
                    loc2 = (
                        response2.headers.get("Location", "")
                        if isinstance(response2, Response)
                        else ""
                    )
                    body2 = getattr(response2, "text", "") or ""
                    raise DataFetchError(
                        f"get weibo detail err: status={getattr(response2, 'status_code', 'N/A')} location={loc2} body={body2}"
                    )
            else:
                raise DataFetchError(
                    f"get weibo detail err: status={response.status_code} location={location} body={body}"
                )

        match = re.search(
            r"var \$render_data = (\[.*?\])\[0\]", response.text, re.DOTALL
        )
        if match:
            render_data_json = match.group(1)
            render_data_dict = json.loads(render_data_json)
            note_detail = render_data_dict[0].get("status")
            note_item = {"mblog": note_detail}
            return note_item

        utils.logger.info(f"[WeiboClient.get_note_info_by_id] 未找到$render_data的值")
        return dict()

    async def get_note_image(self, image_url: str) -> bytes:
        image_url = image_url[8:]  # 去掉 https://
        sub_url = image_url.split("/")
        image_url = ""
        for i in range(len(sub_url)):
            if i == 1:
                image_url += "large/"  # 都获取高清大图
            elif i == len(sub_url) - 1:
                image_url += sub_url[i]
            else:
                image_url += sub_url[i] + "/"
        # 微博图床对外存在防盗链，所以需要代理访问
        # 由于微博图片是通过 i1.wp.com 来访问的，所以需要拼接一下
        final_uri = f"{self._image_agent_host}" f"{image_url}"
        # reuse request wrapper with return_response to get robust timeout/fallback
        response = await self.request(
            "GET", final_uri, headers=self.headers, return_response=True
        )
        try:
            if response.status_code != 200:
                return None
        except AttributeError:
            # fallback returned dict or empty - treat as failure
            return None

        try:
            response.raise_for_status()
            if not response.reason_phrase == "OK":
                utils.logger.error(
                    f"[WeiboClient.get_note_image] request {final_uri} err, res:{response.text}"
                )
                return None
            return response.content
        except (
            httpx.HTTPError
        ) as exc:  # some wrong when call httpx.request method, such as connection error, client error, server error or response status code is not 2xx
            utils.logger.error(
                f"[DouYinClient.get_aweme_media] {exc.__class__.__name__} for {exc.request.url} - {exc}"
            )  # 保留原始异常类型名称，以便开发者调试
            return None

    async def get_creator_container_info(self, creator_id: str) -> Dict:
        """
        获取用户的容器ID, 容器信息代表着真实请求的API路径
            fid_container_id：用户的微博详情API的容器ID
            lfid_container_id：用户的微博列表API的容器ID
        Args:
            creator_id:

        Returns: {

        """
        response = await self.get(f"/u/{creator_id}", return_response=True)
        m_weibocn_params = response.cookies.get("M_WEIBOCN_PARAMS")
        if not m_weibocn_params:
            raise DataFetchError("get containerid failed")
        m_weibocn_params_dict = parse_qs(unquote(m_weibocn_params))
        return {
            "fid_container_id": m_weibocn_params_dict.get("fid", [""])[0],
            "lfid_container_id": m_weibocn_params_dict.get("lfid", [""])[0],
        }

    async def get_creator_info_by_id(self, creator_id: str) -> Dict:
        """
        根据用户ID获取用户详情
        Args:
            creator_id:

        Returns:

        """
        uri = "/api/container/getIndex"
        containerid = f"100505{creator_id}"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator_id,
            "containerid": containerid,
        }
        user_res = await self.get(uri, params)
        return user_res

    async def get_notes_by_creator(
        self,
        creator: str,
        container_id: str,
        since_id: str = "0",
    ) -> Dict:
        """
        获取博主的笔记
        Args:
            creator: 博主ID
            container_id: 容器ID
            since_id: 上一页最后一条笔记的ID
        Returns:

        """

        uri = "/api/container/getIndex"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator,
            "containerid": container_id,
            "since_id": since_id,
        }
        return await self.get(uri, params)

    async def get_all_notes_by_creator_id(
        self,
        creator_id: str,
        container_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取指定用户下的所有发过的帖子，该方法会一直查找一个用户下的所有帖子信息
        Args:
            creator_id:
            container_id:
            crawl_interval:
            callback:

        Returns:

        """
        result = []
        notes_has_more = True
        since_id = ""
        crawler_total_count = 0
        while notes_has_more:
            notes_res = await self.get_notes_by_creator(
                creator_id, container_id, since_id
            )
            if not notes_res:
                utils.logger.error(
                    f"[WeiboClient.get_notes_by_creator] The current creator may have been banned by xhs, so they cannot access the data."
                )
                break
            since_id = notes_res.get("cardlistInfo", {}).get("since_id", "0")
            if "cards" not in notes_res:
                utils.logger.info(
                    f"[WeiboClient.get_all_notes_by_creator] No 'notes' key found in response: {notes_res}"
                )
                break

            notes = notes_res["cards"]
            utils.logger.info(
                f"[WeiboClient.get_all_notes_by_creator] got user_id:{creator_id} notes len : {len(notes)}"
            )
            notes = [note for note in notes if note.get("card_type") == 9]
            if callback:
                await callback(notes)
            await asyncio.sleep(crawl_interval)
            result.extend(notes)
            crawler_total_count += 10
            notes_has_more = (
                notes_res.get("cardlistInfo", {}).get("total", 0) > crawler_total_count
            )
        return result
