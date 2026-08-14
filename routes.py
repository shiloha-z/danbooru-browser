"""Prompt-server routes for the browse panel (ADR-0001).

会话类路由三步:恢复会话 → 动作 → 返回新序列化会话(ADR-0003);无状态代理路由
(图片 / 标签补全)直接转发站点请求。阻塞的站点调用跑在线程里,保持 aiohttp
循环响应。
"""

from __future__ import annotations

import asyncio

from aiohttp import ClientConnectionError, web
from server import PromptServer

from core.browser import Browser
from core.errors import StateError, TransportError
from core.model import Post, SearchConditions
from sites.http import HttpAdapter, image_content_type, is_allowed_image_url


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


def _local_origin_ok(request: web.Request) -> bool:
    """浏览器请求校验 Origin:防任意网页把本机 ComfyUI 当代理跳板(代理来自请求体)。"""
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not origin:  # 非浏览器客户端(无 Origin/Referer)
        return True
    host = request.host
    return origin.startswith(f"http://{host}") or origin.startswith(f"https://{host}")


def setup_routes(server: PromptServer, browser: Browser, http: HttpAdapter) -> None:
    @server.routes.get("/danbooru_browser/image")
    async def image(request: web.Request) -> web.Response:
        """面板图片代理:浏览器直连 CDN 被反爬 403,统一走后端;流式转发,边下边显示。"""
        url = request.query.get("url", "")
        if not is_allowed_image_url(url):
            return web.Response(status=400, text="不允许的图片地址")
        queue: asyncio.Queue = asyncio.Queue()  # 无界:块在内存中最多一张图大小
        loop = asyncio.get_running_loop()
        end = object()

        def producer():
            try:
                for chunk in http.iter_bytes(url):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:  # 网络层任何失败(超时/重置/非 200)都转 502
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, end)

        def terminal(chunk):
            return chunk is end or isinstance(chunk, Exception)

        task = asyncio.create_task(asyncio.to_thread(producer))  # to_thread 返回协程,须 create_task 调度
        first = await queue.get()
        if first is end or isinstance(first, Exception):
            await task
            return web.Response(status=502, text="图片读取失败" if first is end else str(first))
        response = web.StreamResponse(headers={"Content-Type": image_content_type(url)})
        await response.prepare(request)
        try:
            await response.write(first)
            while True:
                chunk = await queue.get()
                if terminal(chunk):
                    break  # 已开始响应,中途失败只能截断(浏览器显示加载失败)
                await response.write(chunk)
            await response.write_eof()
        except (ClientConnectionError, ConnectionResetError):
            pass  # 客户端断开:截断即可
        finally:
            await task  # 等生产者收尾,释放连接
        return response

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

    @server.routes.post("/danbooru_browser/page")
    async def page(request: web.Request) -> web.Response:
        """翻页导航:恢复会话 → goto_page → 序列化(ADR-0003)。"""
        if not _local_origin_ok(request):
            return web.json_response({"error": "非法的请求来源"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        try:
            http.set_proxy(body.get("proxy") or "")
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        try:
            page_no = int(body.get("page"))
        except (TypeError, ValueError):
            return web.json_response({"error": "页码必须是数字"}, status=400)
        if page_no < 1:
            return web.json_response({"error": "页码必须 ≥ 1"}, status=400)
        try:
            session = browser.restore(body.get("state_json", ""))
            result = await asyncio.to_thread(session.goto_page, page_no)
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

    @server.routes.post("/danbooru_browser/action")
    async def action(request: web.Request) -> web.Response:
        """面板动作:模式切换 / 游标 / 列表操作;返回新会话(ADR-0003)。"""
        if not _local_origin_ok(request):
            return web.json_response({"error": "非法的请求来源"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        try:
            http.set_proxy(body.get("proxy") or "")
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        action = body.get("action")
        try:
            session = browser.restore(body.get("state_json", ""))
            if action == "set_mode":
                new_mode = body.get("mode", "")
                if new_mode not in ("manual", "auto", "list"):
                    return web.json_response({"error": "未知模式"}, status=400)
                session.set_mode(new_mode)
            elif action == "reset_cursor":
                session.reset_cursor()
            elif action == "add_to_list":
                session.add_to_list(int(body.get("post_id")))
            elif action == "insert_to_list":
                session.insert_to_list(int(body.get("post_id")), int(body.get("index", 0)))
            elif action == "remove_from_list":
                session.remove_from_list(int(body.get("post_id")))
            elif action == "clear_list":
                session.clear_list()
            else:
                return web.json_response({"error": "未知动作"}, status=400)
        except (StateError, KeyError, ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"state_json": session.serialize()})

    @server.routes.post("/danbooru_browser/search")
    async def search(request: web.Request) -> web.Response:
        if not _local_origin_ok(request):
            return web.json_response({"error": "非法的请求来源"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        try:
            http.set_proxy(body.get("proxy") or "")  # 代理来自节点 widget,全局生效
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
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
