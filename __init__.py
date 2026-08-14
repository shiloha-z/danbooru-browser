"""Danbooru Browser — 浏览 danbooru/gelbooru/civitai 并输出所选帖子的图片 + 提示词 + 元数据。

T1:danbooru 站点 + 手动输出。面板走 prompt-server 路由(ADR-0001),执行器薄适配
(ADR-0003),会话序列化进工作流(ADR-0002)。
"""

import os
import sys

# ComfyUI 只把 custom_nodes 父目录加入 sys.path,包内裸导入(wiring/core/sites)需要
# 本目录自身可解析;测试环境(顶层 import core/sites)已通过 pythonpath 覆盖,此插入无害。
sys.path.insert(0, os.path.dirname(__file__))

try:
    from server import PromptServer
except ImportError:  # 测试环境:无 comfy 依赖,包只做占位(可被 pytest 收集)
    PromptServer = None

if PromptServer is not None:  # 正常 ComfyUI 加载路径
    from wiring import get_browser, get_cache, get_http
    from node import DanbooruBrowserNode, DanbooruBrowserTextPassthrough
    from routes import setup_routes

    NODE_CLASS_MAPPINGS = {
        "DanbooruBrowserNode": DanbooruBrowserNode,
        "DanbooruBrowserTextPassthrough": DanbooruBrowserTextPassthrough,
    }
    NODE_DISPLAY_NAME_MAPPINGS = {
        "DanbooruBrowserNode": "Danbooru Browser",
        "DanbooruBrowserTextPassthrough": "文本(透传)",
    }
    WEB_DIRECTORY = "./web"

    setup_routes(PromptServer.instance, get_browser(), get_http(), get_cache())
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    WEB_DIRECTORY = "./web"
