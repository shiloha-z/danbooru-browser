"""本地凭据(安全约束:绝不进工作流 JSON、绝不跨 core seam、绝不序列化)。

credentials.json 位于节点目录,gitignore;gelbooru API 强制要求
api_key + user_id(2024 起,实测 401)。
"""

from __future__ import annotations

import json
import os
from typing import Any

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "credentials.json")


def get_credentials(site: str) -> dict[str, Any] | None:
    """读取本地凭据;文件缺失 / 未配置该站点返回 None。每次读取,key 变更即时生效。"""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data.get(site)
