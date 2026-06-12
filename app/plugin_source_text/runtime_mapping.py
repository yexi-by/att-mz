"""插件源码当前运行写回映射哈希工具。"""

from __future__ import annotations

import hashlib
import json


def plugin_source_runtime_hash_text(text: str) -> str:
    """计算插件源码单段文本的稳定哈希。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plugin_source_runtime_hash_lines(lines: list[str]) -> str:
    """计算插件源码译文行数组的稳定哈希。"""
    payload = json.dumps(lines, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "plugin_source_runtime_hash_lines",
    "plugin_source_runtime_hash_text",
]
