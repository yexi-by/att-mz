"""Rust 原生扩展与 Python 侧共享的契约版本检查。"""

from __future__ import annotations

NATIVE_CONTRACT_VERSION = 12
_CURRENT_NATIVE_CONTRACT_ERROR_MESSAGE = (
    "Rust 原生扩展不满足当前 Python 契约，请重新构建原生扩展后重试。"
)


def ensure_native_contract_version(native_module: object) -> None:
    """确认已加载的 Rust 原生扩展支持当前 Python 侧 JSON 契约。"""
    version_reader = getattr(native_module, "native_contract_version", None)
    if not callable(version_reader):
        raise RuntimeError(_CURRENT_NATIVE_CONTRACT_ERROR_MESSAGE)
    raw_version = version_reader()
    if not isinstance(raw_version, int) or raw_version < NATIVE_CONTRACT_VERSION:
        raise RuntimeError(_CURRENT_NATIVE_CONTRACT_ERROR_MESSAGE)


__all__: list[str] = [
    "NATIVE_CONTRACT_VERSION",
    "ensure_native_contract_version",
]
