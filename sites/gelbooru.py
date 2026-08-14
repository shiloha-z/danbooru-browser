"""Gelbooru site adapter: dapi post index + file download.

与 danbooru 的差异:API 需要 api_key/user_id 认证(本地凭据文件)、
JSON 结构为 {"post": [...]}、页码 0 起(pid=page-1)、排序用
sort: 元标签、图片域在 img*.gelbooru.com。
"""

from __future__ import annotations

from typing import Any

from core.errors import StateError, TransportError
from core.model import Post, SearchConditions, SearchResult
from core.site import Site, SiteCapabilities

from .credentials import get_credentials
from .http import HttpAdapter

_UNSET = object()  # 哨兵:未注入 → 每次请求实时读凭据文件


def parse_post(d: dict[str, Any], site: str) -> Post:
    file_ext = (d.get("image") or "").rsplit(".", 1)[-1].lower()
    return Post(
        id=int(d["id"]),
        site=site,
        file_url=d.get("file_url") or d.get("sample_url") or "",
        preview_url=d.get("preview_url") or "",
        sample_url=d.get("sample_url") or "",
        tags=tuple((d.get("tags") or "").split()),
        rating=d.get("rating", ""),
        score=int(d.get("score", 0) or 0),
        author=d.get("creator", ""),
        raw=d,
        animated=file_ext in ("webm", "gif", "swf"),
    )


class GelbooruSite:
    BASE_URL = "https://gelbooru.com/index.php"

    # gelbooru 无 OR 运算:评级只能单选(实测 ~ 语法全部无效)
    capabilities = SiteCapabilities(site_name="gelbooru", multi_rating=False)

    def __init__(self, http: HttpAdapter, credentials: dict[str, Any] | None = None):
        self._http = http
        # 注入(测试)或实时读文件:面板设置保存后立即生效
        self._credentials = credentials if credentials is not None else _UNSET

    def _auth_params(self) -> dict[str, str]:
        """本地配置缺失是客户端状态错误(400),不是上游故障(502)。"""
        creds = self._credentials if self._credentials is not _UNSET else get_credentials("gelbooru")
        missing = [k for k in ("user_id", "api_key") if not creds or not creds.get(k)]
        if missing:
            raise StateError(
                f"gelbooru API 需要凭据:在节点目录 credentials.json 配置 {'/'.join(missing)}"
            )
        return {"api_key": str(creds["api_key"]), "user_id": str(creds["user_id"])}

    def search(self, conditions: SearchConditions, page: int) -> SearchResult:
        all_ratings = self.capabilities.ratings  # 能力表是唯一来源(ADR-0003)
        tags = list(conditions.tags)
        if conditions.ratings != frozenset(all_ratings):
            selected = [f"rating:{r}" for r in all_ratings if r in conditions.ratings]
            if len(selected) > 1:
                raise StateError("gelbooru 评级为单选,请只保留一个评级")
            if selected:
                tags.append(selected[0])
        if conditions.sort == "score":
            tags.append("sort:score")
        elif conditions.sort == "random":
            tags.append("sort:random")
        elif conditions.sort == "new":
            tags.append("sort:id")  # gelbooru 最新 = 上传 id 降序(实测 sort:change 是修改序)
        tags += [f"-{t}" for t in conditions.exclude_tags]
        params = {
            "page": "dapi", "s": "post", "q": "index", "json": "1",
            "pid": max(page - 1, 0), "limit": conditions.per_page,
            "tags": " ".join(tags),
            **self._auth_params(),
        }
        data = self._http.get_json(f"{self.BASE_URL}", params=params)
        posts = tuple(parse_post(d, "gelbooru") for d in (data.get("post") or []) if isinstance(d, dict))
        return SearchResult(posts=posts, page=page, has_next=len(posts) >= conditions.per_page)

    def fetch_image(self, post: Post, url: str | None = None) -> bytes:
        return self._http.get_bytes(url or post.file_url)
