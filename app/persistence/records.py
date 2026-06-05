"""多游戏数据库对外记录模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.language import SourceLanguage, TargetLanguage
from app.rule_review import RuleReviewDomain
from app.rmmz.schema import EngineKind, ItemType


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
class RegistryDatabaseIssue:
    """注册表扫描中单个不可用数据库的问题。"""

    db_path: Path
    message: str


@dataclass(slots=True)
class RuleReviewStateRecord:
    """数据库中保存的外部规则空结果审查状态。"""

    rule_domain: RuleReviewDomain
    scope_hash: str
    reviewed_empty: bool
    updated_at: str


@dataclass(slots=True)
class TextIndexMetadata:
    """当前翻译源视图索引的全局元信息。"""

    source_snapshot_fingerprint: str
    rules_fingerprint: str
    item_count: int
    created_at: str
    workflow_gate_scope_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TextIndexItemRecord:
    """当前翻译源视图中的单个文本范围索引项。"""

    location_path: str
    item_type: ItemType
    role: str | None
    original_lines: list[str]
    source_line_paths: list[str]
    source_type: str
    source_file: str
    writable: bool
    source_snapshot_fingerprint: str
    rules_fingerprint: str
    locator_json: str


@dataclass(slots=True)
class TextIndexScopeSummaryRecord:
    """当前文本范围索引的静态范围摘要。"""

    total_count: int
    active_count: int
    writable_count: int
    unwritable_count: int
    stale_rule_count: int
    native_thread_count: int


@dataclass(slots=True)
class TextIndexDomainSummaryRecord:
    """当前文本范围索引按来源域汇总的静态事实。"""

    domain: str
    item_count: int
    active_count: int
    writable_count: int
    unwritable_count: int
    inactive_rule_hit_count: int


@dataclass(slots=True)
class TextIndexRuleHitSummaryRecord:
    """当前文本范围索引按规则命中汇总的静态事实。"""

    domain: str
    rule_key: str
    hit_count: int
    extractable_count: int
    writable_count: int
    unwritable_count: int


@dataclass(slots=True)
class TextIndexInvalidationRecord:
    """文本范围索引失效原因记录。"""

    reason_key: str
    detail: str
    created_at: str
