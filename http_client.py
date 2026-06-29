"""HTTP 客户端封装：基于 httpx，支持 Cookie 管理和 JSONP 解析。

每个学生一个 HttpClient 实例，独立 Cookie Jar，实现 Worker 隔离。
Referer 支持两种模式：实例级（set_referer）和按请求级（referer 参数），
按请求级优先，避免并发任务互相覆盖。
"""
import json
import logging
import re
from typing import Any, Optional

import httpx


class HttpClient:
    """HTTP 客户端：封装 httpx.AsyncClient，自动管理 Cookie。"""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._referer: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def open(self) -> None:
        """初始化 httpx 客户端。重复调用时先关闭旧实例。"""
        if self._client is not None:
            await self.close()
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=self.DEFAULT_HEADERS,
            verify=True,
        )

    async def close(self) -> None:
        """关闭客户端。用 try/finally 确保 _client 置 None。"""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                self.logger.warning(f"HttpClient.close 异常: {e}")
            finally:
                self._client = None

    def set_referer(self, url: str) -> None:
        """设置后续请求的默认 Referer（实例级）。

        注意：并发场景下应优先使用 get/post 的 referer 参数。
        """
        self._referer = url

    def _build_headers(
        self,
        extra: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> dict:
        headers = {}
        # 按请求级 referer 优先于实例级
        effective_referer = referer if referer is not None else self._referer
        if effective_referer:
            headers["Referer"] = effective_referer
        if extra:
            headers.update(extra)
        return headers

    async def get(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> httpx.Response:
        """GET 请求。

        Args:
            referer: 按请求级 Referer，优先于 set_referer 设置的实例级 Referer
        """
        if not self._client:
            raise RuntimeError("HttpClient 未初始化，请先调用 open()")
        resp = await self._client.get(
            url, params=params, headers=self._build_headers(headers, referer)
        )
        return resp

    async def post(
        self,
        url: str,
        data: Optional[Any] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> httpx.Response:
        """POST 请求。

        Args:
            url: 请求 URL
            data: 请求体（dict 表示表单，str 表示原始 body）
            headers: 额外请求头
            params: URL query 参数
            referer: 按请求级 Referer，优先于 set_referer 设置的实例级 Referer
        """
        if not self._client:
            raise RuntimeError("HttpClient 未初始化，请先调用 open()")

        req_headers = self._build_headers(headers, referer)
        if isinstance(data, dict) and "Content-Type" not in req_headers:
            req_headers["Content-Type"] = (
                "application/x-www-form-urlencoded; charset=UTF-8"
            )
        if "X-Requested-With" not in req_headers:
            req_headers["X-Requested-With"] = "XMLHttpRequest"

        resp = await self._client.post(
            url, data=data, headers=req_headers, params=params
        )
        return resp

    async def get_text(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> str:
        """GET 请求并返回文本。"""
        resp = await self.get(url, params, headers, referer)
        return resp.text

    async def get_jsonp(
        self,
        url: str,
        params: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> Optional[dict]:
        """GET 请求并解析 JSONP 响应为 dict。

        JSONP 格式：/**/ jQuery19105964540793563706_xxx({...});
        或：success_jsonpcallback({...});
        """
        text = await self.get_text(url, params, referer=referer)
        return parse_jsonp(text)

    def get_cookies(self) -> dict:
        """获取当前所有 Cookie（name→value）。"""
        if not self._client:
            return {}
        return {c.name: c.value for c in self._client.cookies.jar}

    def get_cookie(self, name: str) -> Optional[str]:
        """获取指定 Cookie 值。"""
        return self.get_cookies().get(name)


def parse_jsonp(text: str) -> Optional[dict]:
    """解析 JSONP 响应为 dict。

    支持格式：
        /**/ jQuery19105964540793563706_xxx({...});
        success_jsonpcallback({...});
        {...}（纯 JSON）
    """
    if not text:
        return None

    text = text.strip()

    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # 贪婪匹配最外层 {...}（JSONP 响应只有一个 callback 包裹，嵌套 JSON 需要贪婪到最后的 }）
    match = re.search(r"\((\{.*\})\)\s*;?\s*$", text, re.S)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
