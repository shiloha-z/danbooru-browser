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


def save_credentials(site: str, fields: dict[str, Any]) -> None:
    """合并写入本地凭据(原子替换);非空字段覆盖,空字段保持原值。"""
    data: dict[str, Any] = {}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    entry = dict(data.get(site) or {})
    for key, value in fields.items():
        if value:
            entry[key] = value
    data[site] = entry
    _write(data)


def clear_credentials(site: str) -> None:
    """删除站点的全部凭据条目。"""
    data: dict[str, Any] = {}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    data.pop(site, None)
    _write(data)


def _write(data: dict[str, Any]) -> None:
    tmp = f"{_CONFIG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _CONFIG_PATH)
