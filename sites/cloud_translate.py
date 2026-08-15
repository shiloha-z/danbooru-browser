"""云翻译后端(移植自参考包,自包含):百度/Google 免费、微软、OpenAI 兼容 LLM。

结果缓存到 data/cloud_translations.json(仅 tag 格式,长句不缓存)。
请求经 HttpAdapter 语义外的原生 requests(翻译服务非站点 API,不走限流)。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading

import requests

_CLOUD_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cloud_translations.json",
)
_cloud_cache: dict[str, str] = {}
_cloud_cache_lock = threading.Lock()
_dirty = False

_TAG_RE = re.compile(r'^[a-z][a-z0-9]*(_[a-z][a-z0-9]*)*$')


def _load_cloud_cache():
    global _cloud_cache, _dirty
    try:
        if os.path.exists(_CLOUD_CACHE_FILE):
            with open(_CLOUD_CACHE_FILE, "r", encoding="utf-8") as f:
                _cloud_cache = json.load(f)
    except Exception:
        _cloud_cache = {}
    _dirty = False


def _save_cloud_cache():
    global _dirty
    if not _dirty:
        return
    with _cloud_cache_lock:
        try:
            os.makedirs(os.path.dirname(_CLOUD_CACHE_FILE), exist_ok=True)
            with open(_CLOUD_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_cloud_cache, f, ensure_ascii=False, indent=2)
            _dirty = False
        except Exception:
            pass


def clear_cloud_cache() -> bool:
    global _cloud_cache
    with _cloud_cache_lock:
        _cloud_cache = {}
    try:
        if os.path.exists(_CLOUD_CACHE_FILE):
            os.remove(_CLOUD_CACHE_FILE)
        return True
    except Exception:
        return False


def is_tag(text: str) -> bool:
    """是否像 tag(值得缓存):下划线词或纯英文单词,不含中文/长句。"""
    text = text.strip()
    if not text or len(text) > 200 or "\n" in text:
        return False
    if "_" in text:
        if re.search(r'[一-鿿　-〿＀-￯]', text):
            return False
        return True
    # danbooru 标签常以数字开头(1girl/2boys)
    if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.\'@()/]*$', text) and " " not in text:
        return True
    return False


def translate_via_baidu(texts, api_key, from_lang="en", to_lang="zh"):
    """百度翻译,api_key 格式 appid:secret。"""
    if not api_key or ":" not in api_key:
        return {}
    appid, secret = api_key.split(":", 1)
    results = {}
    base_url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    for text in texts:
        try:
            salt = str(random.randint(32768, 65536))
            sign_str = appid + text + salt + secret
            sign = hashlib.md5(sign_str.encode()).hexdigest()
            params = {"q": text, "from": from_lang, "to": to_lang,
                      "appid": appid, "salt": salt, "sign": sign}
            resp = requests.get(base_url, params=params, timeout=10)
            data = resp.json()
            if "trans_result" in data:
                translated = data["trans_result"][0]["dst"]
                if translated.strip():
                    results[text] = translated.strip()
        except Exception:
            pass
    return results


def translate_via_google(texts, from_lang="en", to_lang="zh-CN"):
    """Google 免费接口(无需 key)。"""
    results = {}
    for text in texts:
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": from_lang, "tl": to_lang, "dt": "t", "q": text}
            resp = requests.get(url, params=params, timeout=10,
                                headers={"User-Agent": "danbooru-browser-comfyui/0.1"})
            if resp.status_code == 200:
                data = resp.json()
                translated = "".join(block[0] for block in data[0])
                if translated.strip():
                    results[text] = translated.strip()
        except Exception:
            pass
    return results


def translate_via_microsoft(texts, api_key=None):
    """Azure Microsoft Translator(免费层 2M 字符/月)。"""
    if not api_key:
        return {}
    results = {}
    for text in texts:
        try:
            url = "https://api.cognitive.microsofttranslator.com/translate"
            params = {"api-version": "3.0", "to": "zh-Hans"}
            headers = {
                "Ocp-Apim-Subscription-Key": api_key,
                "Ocp-Apim-Subscription-Region": "global",
                "Content-Type": "application/json",
                "User-Agent": "danbooru-browser-comfyui/0.1",
            }
            resp = requests.post(url, params=params, headers=headers,
                                 json=[{"Text": text}], timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                translated = data[0]["translations"][0]["text"]
                if translated.strip():
                    results[text] = translated.strip()
        except Exception:
            pass
    return results


def translate_via_llm(texts, base_url, model, api_key, system_prompt=None,
                      from_lang="en", to_lang="zh"):
    """OpenAI 兼容 API 翻译(DeepSeek/自定义)。"""
    if not system_prompt:
        system_prompt = (
            f"你是一个翻译器。请将以下{from_lang}逐行翻译成{to_lang}。"
            "每行格式:原文=译文。绝不合并多行。只输出翻译结果,不要加任何解释。"
        )
    prompt = f"将以下{from_lang}逐行翻译为{to_lang}(严格每行格式:原文=译文,不得跳过):\n" + "\n".join(texts) + "\n"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "danbooru-browser-comfyui/0.1",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    try:
        resp = requests.post(f"{base_url.rstrip('/')}/chat/completions",
                             headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if len(texts) == 1 and "=" not in content:
                return {texts[0]: content}
            results = {}
            for line in content.split("\n"):
                line = line.strip()
                if "=" in line:
                    parts = line.split("=", 1)
                    tag = parts[0].strip()
                    cn = parts[1].strip()
                    if tag and cn:
                        tag_n = tag.replace("\\(", "(").replace("\\)", ")").replace("\\[", "[").replace("\\]", "]")
                        results[tag_n] = cn
            return results
        else:
            print(f"[DBB] LLM翻译失败 status={resp.status_code} body={resp.text[:300]}")
    except Exception as e:
        print(f"[DBB] LLM翻译异常: {e}")
    return {}


def cloud_translate(tags, provider="google", api_key=None, model=None, base_url=None,
                    as_sentence=False, from_lang="en", to_lang="zh"):
    """批量云翻译入口:缓存命中直接返回,其余按 provider 分发。"""
    if not tags:
        return {}
    results = {}
    to_translate = []
    for t in tags:
        if t in _cloud_cache:
            results[t] = _cloud_cache[t]
        else:
            to_translate.append(t)
    if not to_translate:
        return results

    new_results: dict[str, str] = {}
    if provider == "google" or provider.startswith("google"):
        new_results = translate_via_google(to_translate, from_lang, to_lang)
    elif provider == "microsoft" or provider.startswith("microsoft"):
        new_results = translate_via_microsoft(to_translate, api_key)
    elif provider == "baidu" or provider.startswith("baidu"):
        new_results = translate_via_baidu(to_translate, api_key, from_lang, to_lang)
    else:  # deepseek / custom:OpenAI 兼容 LLM
        _tags_only = [t for t in to_translate if is_tag(t)]
        _sentences = [t for t in to_translate if not is_tag(t)]
        sp = (f"你是一个翻译器。请将以下{from_lang}翻译成{to_lang}。直接输出{to_lang}译文,不要加任何解释。"
              if as_sentence or _sentences else None)
        if _tags_only:
            new_results.update(translate_via_llm(_tags_only, base_url, model, api_key, None, from_lang, to_lang))
        if _sentences:
            new_results.update(translate_via_llm(_sentences, base_url, model, api_key, sp or None, from_lang, to_lang))

    global _dirty
    for t, cn in new_results.items():
        results[t] = cn
        if is_tag(t):
            with _cloud_cache_lock:
                _cloud_cache[t] = cn
            _dirty = True
    if _dirty:
        _save_cloud_cache()
    return results


_load_cloud_cache()
