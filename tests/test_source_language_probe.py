"""源语言探测测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.source_language_probe import probe_source_language


@pytest.mark.asyncio
async def test_source_language_probe_recommends_japanese_visible_text(
    minimal_game_dir: Path,
) -> None:
    """源语言探测只按玩家可见文本给日文游戏高置信度建议。"""
    result = await probe_source_language(minimal_game_dir)

    assert result.recommendation == "ja"
    assert result.confidence == "high"
    assert result.japanese_text_count > result.english_text_count
    assert result.samples["ja"]


@pytest.mark.asyncio
async def test_source_language_probe_recommends_english_visible_text(
    minimal_english_game_dir: Path,
) -> None:
    """源语言探测只按玩家可见文本给英文游戏高置信度建议。"""
    result = await probe_source_language(minimal_english_game_dir)

    assert result.recommendation == "en"
    assert result.confidence == "high"
    assert result.english_text_count > result.japanese_text_count
    assert result.samples["en"]
