"""Prompt-server routes for the browse panel (ADR-0001).

会话类路由三步:恢复会话 → 动作 → 返回新序列化会话(ADR-0003);无状态代理路由
(图片 / 标签补全)直接转发站点请求。阻塞的站点调用跑在线程里,保持 aiohttp
循环响应。
"""

from __future__ import annotations

import asyncio

from aiohttp import web
from server import PromptServer

from core.browser import Browser
from core.errors import StateError, TransportError
from core.model import Post, SearchConditions
from sites.http import HttpAdapter, is_allowed_image_url


def display_post(post: Post) -> dict:
    """面板展示数据:预览图 URL + 状态徽标;原始数据已在会话 JSON 里。"""
    raw = post.raw or {}
    preview = raw.get("preview_file_url") or raw.get("large_file_url") or post.file_url
    return {
        "id": post.id,
        "preview_url": preview,
        "rating": post.rating,
        "score": post.score,
        "animated": post.animated,
    }


def setup_routes(server: PromptServer, browser: Browser, http: HttpAdapter) -> None:
    @server.routes.get("/danbooru_browser/image")
    async def image(request: web.Request) -> web.Response:
        """面板缩略图代理:浏览器直连 CDN 会被反爬 403(浏览器 UA 即拒),统一走后端。"""
        url = request.query.get("url", "")
        if not is_allowed_image_url(url):
            return web.Response(status=400, text="不允许的图片地址")
        try:
            data = await asyncio.to_thread(http.get_bytes, url)
        except TransportError as e:
            return web.Response(status=502, text=str(e))
        return web.Response(body=data, content_type="application/octet-stream")

    @server.routes.get("/danbooru_browser/tags")
    async def tags(request: web.Request) -> web.Response:
        """标签补全候选:搜索框输入时的下拉建议(能力表驱动,ADR-0003)。"""
        query = request.query.get("q", "").strip()
        if not query:
            return web.json_response({"tags": []})
        site = browser.site(request.query.get("site", "danbooru"))
        if not site.capabilities.has_tag_autocomplete:
            return web.json_response({"error": "该站点不支持标签补全"}, status=501)
        try:
            names = await asyncio.to_thread(site.autocomplete_tags, query)
        except TransportError as e:
            return web.json_response({"error": str(e)}, status=502)
        return web.json_response({"tags": names})

    @server.routes.post("/danbooru_browser/search")
    async def search(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        try:
            session = browser.restore(body.get("state_json", ""))
            conditions = SearchConditions.from_dict(body.get("conditions") or {})
            result = await asyncio.to_thread(session.search, conditions)
        except (StateError, KeyError, ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except TransportError as e:
            return web.json_response({"error": str(e)}, status=502)
        return web.json_response(
            {
                "state_json": session.serialize(),
                "posts": [display_post(p) for p in result.posts],
                "page": result.page,
                "has_next": result.has_next,
            }
        )
