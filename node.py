"""The ComfyUI executor node: a thin adapter over Browser.next_output.

T1 implements manual mode: the panel's current selection is output on every
queue execution; EMPTY / FAILED / ANIMATED surface as clear errors.
"""

from __future__ import annotations

import json
from io import BytesIO

import numpy as np
import torch
from PIL import Image

from wiring import get_browser, get_http
from core.model import OutputKind


def image_bytes_to_tensor(data: bytes) -> torch.Tensor:
    """JPEG/PNG bytes → ComfyUI IMAGE tensor [1, H, W, 3] float32 0..1."""
    img = Image.open(BytesIO(data)).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


class DanbooruBrowserNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 浏览会话 JSON(搜索条件、已加载页、游标、选中项);面板维护,随工作流序列化。
                # 单行 widget:会话 JSON 很长,多行会让节点撑成巨型文本框。
                "session": ("STRING", {"default": ""}),
                # HTTP 代理地址(host:port 或完整 URL);空 = 系统代理。全局生效:搜索/图片/补全。
                "proxy": ("STRING", {"default": "127.0.0.1:7897"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("IMAGE", "PROMPT", "META", "SESSION")
    FUNCTION = "run"
    CATEGORY = "danbooru_browser"

    def run(self, session: str = "", proxy: str = ""):
        get_http().set_proxy(proxy)  # 代理是全局 adapter 设置,执行时同步(与面板搜索一致)
        output, new_state = get_browser().next_output(session or "")
        if output.kind is OutputKind.IMAGE:
            return {
                # ui 字典是 executed 消息的载体:没有它 ComfyUI 不发 onExecuted,
                # 自动模式推进后的会话就永远写不回 widget
                "ui": {"SESSION": [new_state]},
                "result": (
                    image_bytes_to_tensor(output.image),
                    output.prompt or "",
                    json.dumps(output.metadata, ensure_ascii=False),
                    new_state,
                ),
            }
        # 手动模式:EMPTY / FAILED / ANIMATED 均为明确报错(自动/列表模式的跳过语义在后续票)
        raise RuntimeError(output.reason or f"输出失败: {output.kind.value}")
