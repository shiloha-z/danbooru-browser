"""Site registry: production adapters wired over the injected HTTP client.

T1 registers danbooru only; gelbooru and civitai land with their own tickets.
"""

from __future__ import annotations

from typing import Mapping

from core.site import Site

from .danbooru import DanbooruSite
from .http import HttpAdapter


def build_registry(http: HttpAdapter) -> Mapping[str, Site]:
    return {"danbooru": DanbooruSite(http)}
