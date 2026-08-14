"""Site registry: production adapters wired over the injected HTTP client.

T1 danbooru; T3 gelbooru; civitai lands with its own ticket (T6).
"""

from __future__ import annotations

from typing import Mapping

from core.site import Site

from .civitai import CivitaiSite
from .danbooru import DanbooruSite
from .gelbooru import GelbooruSite
from .http import HttpAdapter


def build_registry(http: HttpAdapter) -> Mapping[str, Site]:
    return {
        "danbooru": DanbooruSite(http),
        "gelbooru": GelbooruSite(http),
        "civitai": CivitaiSite(http),
    }
