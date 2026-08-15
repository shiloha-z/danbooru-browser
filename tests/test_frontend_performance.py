"""Frontend performance regressions that can run without ComfyUI or a browser."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is unavailable")
def test_state_update_and_page_prefetch_do_not_repeat_work():
    probe = Path(__file__).with_name("_perf_probe.mjs")
    result = subprocess.run(
        [NODE, str(probe)],
        cwd=probe.parent.parent,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
