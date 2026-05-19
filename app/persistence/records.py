"""多游戏数据库对外记录模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.language import SourceLanguage, TargetLanguage
from app.rule_review import RuleReviewDomain
from app.rmmz.schema import EngineKind


@dataclass(slots=True)
class GameMetadata:
    """数据库中保存的游戏绑定元数据。"""

    game_title: str
    game_path: Path
    engine_kind: EngineKind
    content_root: Path
    engine_version: str


@dataclass(slots=True)
class LanguageSettings:
    """数据库中保存的当前游戏语言设置。"""

    source_language: SourceLanguage
    target_language: TargetLanguage


@dataclass(slots=True)
class GameRecord:
    """单个已注册游戏的数据库元数据。"""

    game_title: str
    game_path: Path
    db_path: Path
    engine_kind: EngineKind
    content_root: Path
    engine_version: str
    source_language: SourceLanguage
    target_language: TargetLanguage


@dataclass(slots=True)
class RuleReviewStateRecord:
    """数据库中保存的外部规则空结果审查状态。"""

    rule_domain: RuleReviewDomain
    scope_hash: str
    reviewed_empty: bool
    updated_at: str
