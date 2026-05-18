"""RPG Maker 文本布局服务使用的轻量位置模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProtectedSpan:
    """不参与视觉宽度统计的控制片段范围。"""

    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class BoundaryChar:
    """文本边界处可见字符及其所在行列位置。"""

    line_index: int
    char_index: int
    char: str


@dataclass(frozen=True, slots=True)
class WrappingSpan:
    """一组已配对包裹标点在文本中的位置。"""

    left: BoundaryChar
    right: BoundaryChar
    pair: tuple[str, str]
