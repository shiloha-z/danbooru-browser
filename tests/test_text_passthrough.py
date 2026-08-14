"""文本(透传)核心语义(issue #24)。"""

from __future__ import annotations

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
