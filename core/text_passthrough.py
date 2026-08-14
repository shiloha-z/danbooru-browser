"""文本(透传)节点核心语义(移植自 Anima 包,裁剪交互暂停/元数据写回)。

use_input_text 时输出 text,否则输出 prompt_text;芯片模式用 "; " 存块,
输出还原逗号;prompt 模式空时回退 text。
"""

from __future__ import annotations


def passthrough_text(text: str = "", prompt_text: str = "", use_input_text: bool = True) -> str:
    text = text or ""
    prompt_text = prompt_text or ""
    output = (text if use_input_text else prompt_text) or ""
    output = output.replace("; ", ", ")  # 芯片模式的分块分隔符还原为逗号
    if not use_input_text and not prompt_text and text:
        output = text
    return output
