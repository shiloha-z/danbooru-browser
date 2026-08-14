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

from wiring import get_browser
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
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("IMAGE", "PROMPT", "META")
    FUNCTION = "run"
    CATEGORY = "danbooru_browser"

    def run(self, session: str = ""):
        output, _ = get_browser().next_output(session or "")
        if output.kind is OutputKind.IMAGE:
            return (
                image_bytes_to_tensor(output.image),
                output.prompt or "",
                json.dumps(output.metadata, ensure_ascii=False),
            )
        # 手动模式:EMPTY / FAILED / ANIMATED 均为明确报错(自动/列表模式的跳过语义在后续票)
        raise RuntimeError(output.reason or f"输出失败: {output.kind.value}")
