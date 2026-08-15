"""文本(透传)核心语义与暂停模式(issue #24)。"""

from __future__ import annotations

import threading
import time

from core.pt_state import pause_execute
from core.text_passthrough import passthrough_text


class TestPassthrough:
    def test_input_mode_returns_text(self):
        assert passthrough_text(text="1girl, blue_eyes", use_input_text=True) == "1girl, blue_eyes"

    def test_prompt_mode_returns_prompt_text(self):
        assert passthrough_text(text="1girl", prompt_text="masterpiece", use_input_text=False) == "masterpiece"

    def test_chip_separator_normalized(self):
        # 芯片模式用 "; " 分块存储,输出还原为逗号
        assert passthrough_text(text="1girl; long_hair", use_input_text=True) == "1girl, long_hair"

    def test_prompt_mode_empty_falls_back_to_text(self):
        assert passthrough_text(text="1girl", prompt_text="", use_input_text=False) == "1girl"

    def test_empty_everything(self):
        assert passthrough_text() == ""
        assert passthrough_text(use_input_text=False) == ""


class TestPauseMode:
    def test_string_node_id_normalized_to_int(self):
        # UNIQUE_ID 是字符串,pt_continue 路由转 int:键必须匹配,否则暂停卡满超时
        from core import pt_state
        pt_state._status.clear()
        pt_state._edited.clear()
        pt_state._gen.clear()
        notified = []
        results = {}

        def run():
            results["out"] = pt_state.pause_execute(
                "42", "orig", lambda n, g, t: notified.append((n, g, t)), timeout=5,
            )

        t = threading.Thread(target=run)
        t.start()
        for _ in range(50):
            if pt_state._status.get((42, 1)) == "paused":  # 键是 int
                break
            time.sleep(0.02)
        assert notified == [(42, 1, "orig")]
        pt_state._edited[(42, 1)] = "edited"
        pt_state._status[(42, 1)] = "continue"
        t.join(timeout=5)
        assert results["out"] == "edited"

    def test_blocks_until_continue_with_edited_output(self):
        from core import pt_state
        pt_state._status.clear()
        pt_state._edited.clear()
        pt_state._gen.clear()
        notified = []
        results = {}

        def run():
            results["out"] = pause_execute(777, "1girl, original", lambda n, g, t: notified.append((n, g, t)))

        t = threading.Thread(target=run)
        t.start()
        for _ in range(50):
            if pt_state._status.get((777, 1)) == "paused":
                break
            time.sleep(0.02)
        assert notified == [(777, 1, "1girl, original")]  # 已通知前端
        pt_state._edited[(777, 1)] = "1girl, edited"  # 模拟前端编辑
        pt_state._status[(777, 1)] = "continue"
        t.join(timeout=5)
        assert results["out"] == "1girl, edited"  # 取编辑后的输出
