"""文本(透传)暂停模式的跨请求状态(移植自 Anima 包)。

执行中阻塞等待前端确认:node 侧写 paused 并推送 db-pt-show-continue,
前端编辑后 POST pt_continue 写 edited + continue,node 侧苏醒取 edited。
"""

from __future__ import annotations

import time
from typing import Callable

_status: dict[tuple[int, int], str] = {}  # (node_id, gen) -> "paused" | "continue"
_edited: dict[tuple[int, int], str] = {}  # (node_id, gen) -> 前端编辑后的输出
_gen: dict[int, int] = {}  # node_id -> 当前世代


def pause_execute(node_id: int, output: str, notify: Callable[[int, int, str], None],
                  timeout: float = 60.0) -> str:
    """阻塞执行直到前端确认:通知前端 → 等 continue → 取编辑后的输出。

    notify(node_id, gen, text) 由调用方实现(ComfyUI 推送 db-pt-show-continue)。
    timeout 超时后继续未编辑输出:无前端(API 队列/关页)时不永久阻塞。
    """
    gen = _gen.get(node_id, 0) + 1
    _gen[node_id] = gen
    key = (node_id, gen)
    _status[key] = "paused"
    notify(node_id, gen, output)
    deadline = time.monotonic() + timeout
    while _status.get(key) == "paused" and time.monotonic() < deadline:
        time.sleep(0.1)
    if key in _edited:
        output = _edited.pop(key)
    _status.pop(key, None)
    return output
