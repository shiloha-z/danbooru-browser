"""Prompt-server routes for the browse panel (ADR-0001).

Every route is three steps: restore the session from the workflow widget JSON
→ perform the action → return the new serialized session (ADR-0003). Blocking
site calls run in a thread so the aiohttp loop stays responsive.
"""

from __future__ import annotations

import asyncio

from aiohttp import web
from server import PromptServer

from core.browser import Browser
from core.errors import StateError, TransportError
from core.model import Post, SearchConditions


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


def setup_routes(server: PromptServer, browser: Browser) -> None:
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
