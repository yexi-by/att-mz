"""
核心 CLI 翻译编排模块。

本模块串起游戏注册、外部规则导入、正文翻译、已保存译文复用与游戏文件回写。
"""

import asyncio
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from app.application.errors import ApplicationBusinessError, WriteBackGateError
from app.application.file_writer import write_planned_text_file_sources
from app.application.font_replacement import (
    collect_replacement_font_names,
    restore_font_references_from_origin_backups,
)
from app.application.font_replacement.constants import FONTS_DIRECTORY_NAME
from app.application.font_replacement.css import replace_gamefont_css_references
from app.application.font_replacement.files import (
    copy_replacement_font,
)
from app.application.flow_gate import (
    assert_workflow_gate_passed,
    ensure_empty_rule_confirmed,
    event_command_rule_codes_for_setting,
    event_command_rule_scope_hash_for_command_codes,
    format_workflow_gate_error,
    note_tag_rule_scope_hash_for_text_rules,
)
from app.application.runtime import load_runtime_setting
from app.application.rule_import_backup import write_rule_import_translation_backup
from app.application.summaries import (
    EventCommandJsonExportSummary,
    EventCommandRuleImportSummary,
    FontRestoreSummary,
    NoteTagJsonExportSummary,
    NoteTagRuleImportSummary,
    PluginJsonExportSummary,
    PluginRuleImportSummary,
    TerminologyImportSummary,
    TerminologyWriteSummary,
    TextTranslationSummary,
    WriteBackSummary,
)
from app.application.write_back_gate import assert_write_back_quality_passed
from app.config import (
    SettingOverrides,
    load_custom_placeholder_rules_text,
)
from app.config.schemas import Setting
from app.language import SourceLanguage
from app.event_command_text import (
    build_event_command_rule_records_from_import,
    command_matches_filters,
    event_command_rule_key,
    export_event_commands_json_file,
    load_event_command_rule_import_file,
    resolve_event_command_codes,
)
from app.terminology import (
    TerminologyExportSummary,
    TerminologyExtraction,
    TerminologyPromptIndex,
    TerminologyRegistry,
    export_terminology_artifacts,
    load_terminology_glossary,
    load_terminology_registry,
    validate_terminology_bundle,
)
from app.note_tag_text import (
    NoteTagTextExtraction,
    build_note_tag_rule_records_from_import,
    export_note_tag_candidates_file,
    load_note_tag_rule_import_file,
    note_tag_location_path_matches_rule,
)
from app.persistence import GameRegistry, TargetGameSession
from app.persistence.repository import current_timestamp_text
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    plugin_rule_scope_hash,
)
from app.plugin_text import (
    build_plugin_rule_records_from_import,
    export_plugins_json_file,
    load_plugin_rule_import_file,
)
from app.plugin_source_text import (
    ActiveRuntimePluginSourceAudit,
    audit_active_runtime_plugin_source_with_scan_cache,
)
from app.nonstandard_data import audit_active_runtime_nonstandard_data
from app.application.use_cases.translation_run import (
    TranslationProgressState,
    TranslationRunInterrupted,
    TranslationRunLimits,
    build_llm_failure_record,
    build_translation_batches,
    count_translation_items,
    deduplicate_translation_data,
    expand_cached_error_items,
    expand_cached_translation_items,
    filter_pending_translation_data,
    limit_translation_data,
)
from app.rmmz.commands import iter_all_commands
from app.rmmz.schema import (
    GameData,
    GameLayout,
    EventCommandTextRuleRecord,
    NoteTagTextRuleRecord,
    NonstandardDataTextRuleRecord,
    PlaceholderRuleRecord,
    PLUGINS_FILE_NAME,
    PluginSourceRuntimeWriteMapRecord,
    PluginTextRuleRecord,
    StructuredPlaceholderRuleRecord,
    TranslationItem,
    TranslationRunRecord,
)
from app.rmmz.control_codes import CustomPlaceholderRule, StructuredPlaceholderRule
from app.llm import LLMHandler, LLMRequestFailure
from app.native_quality import native_thread_count
from app.native_write_plan import build_native_write_back_plan, build_native_write_back_setting_payload
from app.rmmz.text_rules import JsonObject, TextRules
from app.regex_contract import RegexContractValidationError
from app.translation import TextTranslation, TranslationBatch, TranslationCache
from app.rmmz.game_file_view import GameFileView
from app.rmmz.loader import (
    load_active_runtime_game_data,
    load_game_data_for_view,
    read_game_title,
    resolve_game_directory,
    resolve_game_layout,
)
from app.observability.logging import logger
from app.utils.config_loader_utils import load_setting
from app.source_residual import SourceResidualRuleSet
from app.text_index import (
    collect_text_index_external_rule_gate_errors,
    detect_text_index_invalidations,
    rebuild_text_index as rebuild_persistent_text_index,
    text_index_items_to_translation_data_map,
)
from app.text_scope import TextScopeResult, TextScopeService, collect_translation_data_paths
from app.rmmz.source_snapshot import validate_source_snapshot_manifest


type WriteRuntimeMode = Literal["write_back", "rebuild_active_runtime", "write_terminology"]
type WriteProgressCallbacks = (
    tuple[Callable[[int, int], None], Callable[[int], None]]
    | tuple[Callable[[int, int], None], Callable[[int], None], Callable[[str], None]]
)


@dataclass(frozen=True, slots=True)
class PreparedWriteOperation:
    """写入游戏文件前已经完成门禁检查的上下文。"""

    game_data: GameData
    setting: Setting
    text_rules: TextRules
    translated_items: list[TranslationItem]
    writable_location_paths: list[str]
    scope: TextScopeResult
    pre_write_check_ms: int = 0


def _unpack_write_progress_callbacks(
    callbacks: WriteProgressCallbacks,
) -> tuple[Callable[[int, int], None], Callable[[int], None], Callable[[str], None]]:
    """拆分写文件进度回调和阶段状态回调。"""
    if len(callbacks) == 3:
        return callbacks[0], callbacks[1], callbacks[2]
    progress_callbacks = callbacks
    set_progress, advance_progress = progress_callbacks

    def set_status(status: str) -> None:
        logger.debug(f"[tag.phase]写文件阶段[/tag.phase] {status}")

    return set_progress, advance_progress, set_status


def _translation_paths_matching_note_rules(
    *,
    translated_items: list[TranslationItem],
    rule_records: list[NoteTagTextRuleRecord],
) -> set[str]:
    """从已保存译文中找出属于指定 Note 标签规则的定位路径。"""
    return {
        item.location_path
        for item in translated_items
        for rule_record in rule_records
        if note_tag_location_path_matches_rule(
            location_path=item.location_path,
            rule_record=rule_record,
        )
    }


def _note_tag_rule_prefixes(rule_records: list[NoteTagTextRuleRecord]) -> list[str]:
    """返回 Note 标签规则影响的已保存译文路径前缀。"""
    return sorted({f"{record.file_name}/" for record in rule_records})


class TranslationHandler:
    """核心 CLI 翻译业务总编排器。"""

    def __init__(
        self,
        game_registry: GameRegistry,
        llm_handler: LLMHandler,
    ) -> None:
        """初始化编排器。"""
        self.game_registry: GameRegistry = game_registry
        self.llm_handler: LLMHandler = llm_handler

    @classmethod
    async def create(cls) -> Self:
        """创建编排器，不打开任何游戏数据库。"""
        game_registry = GameRegistry()
        llm_handler = LLMHandler()
        logger.info("[tag.phase]编排器初始化完成[/tag.phase] 数据库将在目标命令执行时按需打开")
        return cls(game_registry, llm_handler)

    async def close(self) -> None:
        """释放编排器持有的运行时资源。"""
        self.llm_handler.clean()

    def _load_runtime_setting(
        self,
        setting_overrides: SettingOverrides | None = None,
        source_language: SourceLanguage | None = None,
    ) -> Setting:
        """加载配置并按本轮命令重置模型服务。"""
        return load_runtime_setting(
            self.llm_handler,
            overrides=setting_overrides,
            source_language=source_language,
        )

    def _load_setting(
        self,
        setting_overrides: SettingOverrides | None = None,
        source_language: SourceLanguage | None = None,
    ) -> Setting:
        """加载当前配置，不改动模型服务连接状态。"""
        return load_setting(overrides=setting_overrides, source_language=source_language)

    def _load_text_rules(
        self,
        setting: Setting,
        custom_placeholder_rules_text: str | None = None,
        placeholder_rule_records: list[PlaceholderRuleRecord] | None = None,
        structured_placeholder_rule_records: list[StructuredPlaceholderRuleRecord] | None = None,
    ) -> TextRules:
        """加载文本过滤规则、自定义占位符规则和结构化占位符规则。"""
        if custom_placeholder_rules_text is not None:
            custom_rules = load_custom_placeholder_rules_text(custom_placeholder_rules_text)
            source_label = "CLI 参数"
        elif placeholder_rule_records is not None:
            custom_rules = tuple(
                CustomPlaceholderRule.create(
                    pattern_text=record.pattern_text,
                    placeholder_template=record.placeholder_template,
                )
                for record in placeholder_rule_records
            )
            source_label = "当前游戏数据库"
        else:
            custom_rules = ()
            source_label = "空规则"

        structured_rules = self._build_structured_placeholder_rules(
            structured_placeholder_rule_records or []
        )
        if custom_rules:
            logger.info(f"[tag.phase]已加载自定义占位符规则[/tag.phase] 来源 {source_label} 数量 [tag.count]{len(custom_rules)}[/tag.count] 条")
        elif custom_placeholder_rules_text is not None:
            logger.info("[tag.skip]CLI 指定的自定义占位符规则为空对象[/tag.skip]")
        if structured_rules:
            logger.info(f"[tag.phase]已加载结构化占位符规则[/tag.phase] 来源 当前游戏数据库 数量 [tag.count]{len(structured_rules)}[/tag.count] 条")
        return TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=custom_rules,
            structured_placeholder_rules=structured_rules,
        )

    def _build_structured_placeholder_rules(
        self,
        records: list[StructuredPlaceholderRuleRecord],
    ) -> tuple[StructuredPlaceholderRule, ...]:
        """把数据库结构化占位符规则转换成运行时规则。"""
        return tuple(
            StructuredPlaceholderRule.create(
                rule_name=record.rule_name,
                rule_type=record.rule_type,
                pattern_text=record.pattern_text,
                translatable_group=record.translatable_group,
                protected_groups=dict(record.protected_groups),
            )
            for record in records
        )

    async def _load_session_profile_text_rules(self, session: TargetGameSession) -> TextRules:
        """按当前配置和已导入占位符规则构造文本判断规则。"""
        setting = self._load_setting(source_language=session.source_language)
        placeholder_records = await session.read_placeholder_rules()
        structured_placeholder_records = await session.read_structured_placeholder_rules()
        return self._load_text_rules(
            setting,
            placeholder_rule_records=placeholder_records,
            structured_placeholder_rule_records=structured_placeholder_records,
        )

    async def _load_session_game_data(
        self,
        session: TargetGameSession,
        *,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        """加载目标游戏数据并绑定到当前命令会话。"""
        game_data = await load_game_data_for_view(
            session.game_path,
            source_view=GameFileView.TRANSLATION_SOURCE,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )
        snapshot_records = await session.read_source_snapshot_records()
        if not snapshot_records:
            raise ApplicationBusinessError("当前游戏缺少可信源快照 manifest，请使用干净游戏目录重新执行 add-game")
        validate_source_snapshot_manifest(
            layout=game_data.layout,
            records=snapshot_records,
        )
        session.set_game_data(game_data)
        return session.require_game_data()

    async def resolve_game_title_by_path(self, game_path: str | Path) -> str:
        """根据已注册游戏目录解析可用于 CLI 的游戏标题。"""
        return await self.game_registry.resolve_registered_title_by_path(game_path)

    async def _rebuild_text_index_for_translation(
        self,
        *,
        session: TargetGameSession,
        setting: Setting,
        text_rules: TextRules,
        callbacks: tuple[
            Callable[[int, int], None],
            Callable[[int], None],
            Callable[[str], None],
        ],
    ) -> tuple[JsonObject, str | None]:
        """为 `translate --max-items` 自动重建索引，返回报告摘要和阻断原因。"""
        set_progress, advance_progress, set_status = callbacks
        started_at = time.perf_counter()
        stage_started_at = started_at
        stage_timings: dict[str, int] = {}

        def finish_stage(stage_name: str) -> None:
            nonlocal stage_started_at
            now = time.perf_counter()
            stage_timings[stage_name] = int((now - stage_started_at) * 1000)
            stage_started_at = now

        def rebuild_summary(*, index_status: str, indexed_count: int) -> JsonObject:
            return {
                "index_status": index_status,
                "indexed_count": indexed_count,
                "index_item_count": indexed_count,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "stage_timings": dict(stage_timings),
                "native_thread_count": native_thread_count(),
            }

        set_progress(0, 5)
        set_status("重建文本范围索引：加载翻译源视图")
        plugin_source_records = await session.read_plugin_source_text_rules()
        game_data = await self._load_session_game_data(
            session,
            include_plugin_source_files=bool(plugin_source_records),
        )
        translated_items = await session.read_translated_items()
        advance_progress(1)
        finish_stage("load_translation_source")

        set_status("重建文本范围索引：构建统一文本范围")
        try:
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
                include_write_probe=True,
            )
        except RegexContractValidationError as error:
            finish_stage("build_text_scope")
            return rebuild_summary(index_status="not_rebuilt", indexed_count=0), (
                f"文本规则检查没通过，不能重建文本范围索引: {error}"
            )
        finish_stage("build_text_scope")
        if scope.write_back_probe_error:
            return rebuild_summary(index_status="not_rebuilt", indexed_count=0), scope.write_back_probe_error
        if scope.stale_plugin_rules:
            return rebuild_summary(index_status="not_rebuilt", indexed_count=0), (
                f"发现 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导出并导入插件规则"
            )
        if scope.unwritable_entries:
            return rebuild_summary(index_status="not_rebuilt", indexed_count=0), (
                f"发现 {len(scope.unwritable_entries)} 条当前文本无法写进游戏文件，请先运行 audit-coverage 查看明细"
            )
        advance_progress(1)

        set_status("重建文本范围索引：写入数据库")
        metadata = await rebuild_persistent_text_index(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            scope=scope,
        )
        advance_progress(1)
        finish_stage("write_text_index")
        set_progress(5, 5)
        return rebuild_summary(index_status="rebuilt", indexed_count=metadata.item_count), None

    async def add_game(
        self,
        game_path: str | Path,
        source_language: SourceLanguage,
    ) -> str:
        """注册一个新的游戏。"""
        resolved_game_path = resolve_game_directory(game_path)
        layout = resolve_game_layout(resolved_game_path)
        game_title = read_game_title(resolved_game_path)
        record = await self.game_registry.register_game(
            resolved_game_path,
            source_language=source_language,
        )
        logger.success(f"[tag.success]游戏已加入核心 CLI[/tag.success] 标题 [tag.count]{game_title}[/tag.count] 引擎 [tag.count]{layout.engine_label}[/tag.count] 源语言 [tag.count]{source_language}[/tag.count] 数据目录 [tag.path]{layout.data_dir}[/tag.path] 路径 [tag.path]{record.game_path}[/tag.path]")
        return game_title

    async def import_plugin_rules(
        self,
        game_title: str,
        input_path: Path,
        confirm_empty: bool = False,
    ) -> PluginRuleImportSummary:
        """把外部插件规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            text_rules = await self._load_session_profile_text_rules(session)
            import_file = await load_plugin_rule_import_file(input_path)
            rule_records = build_plugin_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
                text_rules=text_rules,
            )
            if not rule_records:
                ensure_empty_rule_confirmed(
                    rule_label="插件规则",
                    confirm_empty=confirm_empty,
                )
            old_rules = {
                rule.plugin_index: rule
                for rule in await session.read_plugin_text_rules()
            }
            deleted_translation_items = 0
            deleted_translation_backup_path: str | None = None
            stale_prefixes: set[str] = set()
            for rule_record in rule_records:
                old_rule = old_rules.get(rule_record.plugin_index)
                if self._should_refresh_plugin_translation_items(old_rule, rule_record):
                    stale_prefixes.add(f"{PLUGINS_FILE_NAME}/{rule_record.plugin_index}/")
            new_plugin_indexes = {rule.plugin_index for rule in rule_records}
            for plugin_index in sorted(set(old_rules) - new_plugin_indexes):
                stale_prefixes.add(f"{PLUGINS_FILE_NAME}/{plugin_index}/")
            if stale_prefixes:
                stale_items = await session.read_translated_items_by_prefixes(sorted(stale_prefixes))
                backup = await write_rule_import_translation_backup(
                    game_title=game_title,
                    domain="plugin-rules",
                    items=stale_items,
                )
                if backup is not None:
                    deleted_translation_backup_path = backup.backup_path
                deleted_translation_items = await session.delete_translation_items_by_prefixes(
                    sorted(stale_prefixes),
                )
            await session.replace_plugin_text_rules(rule_records)
            if rule_records:
                await session.delete_rule_review_state(rule_domain=PLUGIN_TEXT_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
                    scope_hash=plugin_rule_scope_hash(game_data),
                    reviewed_empty=True,
                )
        imported_rule_count = sum(len(record.path_templates) for record in rule_records)
        logger.success(f"[tag.success]插件规则导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 插件 [tag.count]{len(rule_records)}[/tag.count] 个，规则 [tag.count]{imported_rule_count}[/tag.count] 条，清理失效译文 [tag.count]{deleted_translation_items}[/tag.count] 条")
        if deleted_translation_backup_path is not None:
            logger.warning(f"[tag.warning]已备份被清理的插件译文[/tag.warning] 文件 [tag.path]{deleted_translation_backup_path}[/tag.path]")
        return PluginRuleImportSummary(
            imported_plugin_count=len(rule_records),
            imported_rule_count=imported_rule_count,
            deleted_translation_items=deleted_translation_items,
            deleted_translation_backup_path=deleted_translation_backup_path,
        )

    async def export_plugins_json(
        self,
        game_title: str,
        output_path: Path,
    ) -> PluginJsonExportSummary:
        """把当前游戏的 plugins.js 导出为纯 JSON。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            resolved_output_path = output_path.resolve()
            await export_plugins_json_file(game_data=game_data, output_path=resolved_output_path)
            logger.success(f"[tag.success]插件配置 JSON 导出完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 插件 [tag.count]{len(game_data.plugins_js)}[/tag.count] 个 文件 [tag.path]{resolved_output_path}[/tag.path]")
            return PluginJsonExportSummary(
                output_path=str(resolved_output_path),
                plugin_count=len(game_data.plugins_js),
            )

    async def export_event_commands_json(
        self,
        game_title: str,
        output_path: Path,
        command_codes: set[int] | None,
    ) -> EventCommandJsonExportSummary:
        """把指定事件指令的原始参数导出为 JSON。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            resolved_output_path = output_path.resolve()
            default_command_codes: list[int] | None = None
            if command_codes is None:
                setting = self._load_setting(source_language=session.source_language)
                default_command_codes = setting.event_command_text.default_codes_for_engine(
                    game_data.layout.engine_kind
                )
            effective_command_codes = resolve_event_command_codes(
                command_codes=command_codes,
                default_command_codes=default_command_codes,
            )
            command_count = await export_event_commands_json_file(
                game_data=game_data,
                output_path=resolved_output_path,
                command_codes=effective_command_codes,
            )
            code_label = ", ".join(map(str, sorted(effective_command_codes)))
            logger.success(f"[tag.success]事件指令参数 JSON 导出完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 编码 [tag.count]{code_label}[/tag.count] 指令 [tag.count]{command_count}[/tag.count] 条 文件 [tag.path]{resolved_output_path}[/tag.path]")
            return EventCommandJsonExportSummary(
                output_path=str(resolved_output_path),
                command_codes=list(sorted(effective_command_codes)),
                command_count=command_count,
            )

    async def export_note_tag_candidates(
        self,
        game_title: str,
        output_path: Path,
    ) -> NoteTagJsonExportSummary:
        """把当前游戏 data Note 标签候选导出为 JSON。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = self._load_setting(source_language=session.source_language)
            game_data = await self._load_session_game_data(session)
            text_rules = self._load_text_rules(
                setting=setting,
                placeholder_rule_records=await session.read_placeholder_rules(),
                structured_placeholder_rule_records=await session.read_structured_placeholder_rules(),
            )
            resolved_output_path = output_path.resolve()
            report = await export_note_tag_candidates_file(
                game_data=game_data,
                output_path=resolved_output_path,
                text_rules=text_rules,
            )
        logger.success(f"[tag.success]Note 标签候选 JSON 导出完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 候选标签 [tag.count]{report.candidate_tag_count}[/tag.count] 个 文件 [tag.path]{resolved_output_path}[/tag.path]")
        return NoteTagJsonExportSummary(
            output_path=str(resolved_output_path),
            candidate_tag_count=report.candidate_tag_count,
            translatable_value_count=report.translatable_value_count,
        )

    async def import_event_command_rules(
        self,
        game_title: str,
        input_path: Path,
        confirm_empty: bool = False,
        command_codes: set[int] | None = None,
    ) -> EventCommandRuleImportSummary:
        """把外部事件指令规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            import_file = await load_event_command_rule_import_file(input_path)
            rule_records = build_event_command_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
            )
            empty_review_scope_hash: str | None = None
            if not rule_records:
                ensure_empty_rule_confirmed(
                    rule_label="事件指令规则",
                    confirm_empty=confirm_empty,
                )
                if command_codes is None:
                    setting = self._load_setting(source_language=session.source_language)
                    effective_command_codes = event_command_rule_codes_for_setting(
                        game_data=game_data,
                        setting=setting,
                    )
                else:
                    effective_command_codes = resolve_event_command_codes(
                        command_codes=command_codes,
                        default_command_codes=None,
                    )
                empty_review_scope_hash = event_command_rule_scope_hash_for_command_codes(
                    game_data=game_data,
                    command_codes=effective_command_codes,
                )
            old_rules = {
                event_command_rule_key(rule): rule
                for rule in await session.read_event_command_text_rules()
            }
            deleted_translation_items = 0
            deleted_translation_backup_path: str | None = None
            stale_prefixes: set[str] = set()
            for rule_record in rule_records:
                rule_key = event_command_rule_key(rule_record)
                old_rule = old_rules.get(rule_key)
                if self._should_refresh_event_command_translation_items(old_rule, rule_record):
                    if old_rule is not None:
                        stale_prefixes.update(
                            self._event_command_rule_prefixes(game_data=game_data, rule_record=old_rule),
                        )
                    stale_prefixes.update(
                        self._event_command_rule_prefixes(game_data=game_data, rule_record=rule_record),
                    )
            new_rule_keys = {event_command_rule_key(rule) for rule in rule_records}
            for rule_key, old_rule in old_rules.items():
                if rule_key not in new_rule_keys:
                    stale_prefixes.update(
                        self._event_command_rule_prefixes(game_data=game_data, rule_record=old_rule),
                    )
            if stale_prefixes:
                stale_items = await session.read_translated_items_by_prefixes(sorted(stale_prefixes))
                backup = await write_rule_import_translation_backup(
                    game_title=game_title,
                    domain="event-command-rules",
                    items=stale_items,
                )
                if backup is not None:
                    deleted_translation_backup_path = backup.backup_path
                deleted_translation_items = await session.delete_translation_items_by_prefixes(
                    sorted(stale_prefixes),
                )
            await session.replace_event_command_text_rules(rule_records)
            if rule_records:
                await session.delete_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)
            else:
                if empty_review_scope_hash is None:
                    raise RuntimeError("事件指令空规则确认范围未计算")
                await session.replace_rule_review_state(
                    rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
                    scope_hash=empty_review_scope_hash,
                    reviewed_empty=True,
                )
        imported_path_rule_count = sum(len(record.path_templates) for record in rule_records)
        logger.success(f"[tag.success]事件指令规则导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 规则组 [tag.count]{len(rule_records)}[/tag.count] 个，路径规则 [tag.count]{imported_path_rule_count}[/tag.count] 条，清理失效译文 [tag.count]{deleted_translation_items}[/tag.count] 条")
        if deleted_translation_backup_path is not None:
            logger.warning(f"[tag.warning]已备份被清理的事件指令译文[/tag.warning] 文件 [tag.path]{deleted_translation_backup_path}[/tag.path]")
        return EventCommandRuleImportSummary(
            imported_rule_group_count=len(rule_records),
            imported_path_rule_count=imported_path_rule_count,
            deleted_translation_items=deleted_translation_items,
            deleted_translation_backup_path=deleted_translation_backup_path,
        )

    async def import_note_tag_rules(
        self,
        game_title: str,
        input_path: Path,
        confirm_empty: bool = False,
    ) -> NoteTagRuleImportSummary:
        """把外部 Note 标签规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = self._load_setting(source_language=session.source_language)
            game_data = await self._load_session_game_data(session)
            text_rules = self._load_text_rules(
                setting=setting,
                placeholder_rule_records=await session.read_placeholder_rules(),
                structured_placeholder_rule_records=await session.read_structured_placeholder_rules(),
            )
            import_file = await load_note_tag_rule_import_file(input_path)
            rule_records = build_note_tag_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
                text_rules=text_rules,
            )
            if not rule_records:
                ensure_empty_rule_confirmed(
                    rule_label="Note 标签规则",
                    confirm_empty=confirm_empty,
                )
            old_rules = {
                rule.file_name: rule
                for rule in await session.read_note_tag_text_rules()
            }
            old_note_items = await session.read_translated_items_by_prefixes(
                _note_tag_rule_prefixes(list(old_rules.values()))
            )
            old_note_paths = _translation_paths_matching_note_rules(
                translated_items=old_note_items,
                rule_records=list(old_rules.values()),
            )
            new_note_paths = collect_translation_data_paths(
                NoteTagTextExtraction(
                    game_data=game_data,
                    rule_records=rule_records,
                    text_rules=text_rules,
                ).extract_all_text()
            )
            changed_rule_count = sum(
                1
                for rule_record in rule_records
                if self._should_refresh_note_tag_translation_items(old_rules.get(rule_record.file_name), rule_record)
            )
            removed_rule_count = len(set(old_rules) - {rule.file_name for rule in rule_records})
            stale_paths = sorted(old_note_paths - new_note_paths)
            deleted_translation_items = 0
            deleted_translation_backup_path: str | None = None
            if stale_paths and (changed_rule_count or removed_rule_count):
                stale_items = await session.read_translated_items_by_paths(stale_paths)
                backup = await write_rule_import_translation_backup(
                    game_title=game_title,
                    domain="note-tag-rules",
                    items=stale_items,
                )
                if backup is not None:
                    deleted_translation_backup_path = backup.backup_path
                deleted_translation_items = await session.delete_translation_items_by_paths(stale_paths)
            await session.replace_note_tag_text_rules(rule_records)
            if rule_records:
                await session.delete_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                    scope_hash=note_tag_rule_scope_hash_for_text_rules(
                        game_data=game_data,
                        text_rules=text_rules,
                    ),
                    reviewed_empty=True,
                )
        imported_tag_count = sum(len(record.tag_names) for record in rule_records)
        logger.success(f"[tag.success]Note 标签规则导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 文件 [tag.count]{len(rule_records)}[/tag.count] 个，标签 [tag.count]{imported_tag_count}[/tag.count] 个，清理失效译文 [tag.count]{deleted_translation_items}[/tag.count] 条")
        if deleted_translation_backup_path is not None:
            logger.warning(f"[tag.warning]已备份被清理的 Note 标签译文[/tag.warning] 文件 [tag.path]{deleted_translation_backup_path}[/tag.path]")
        return NoteTagRuleImportSummary(
            imported_file_count=len(rule_records),
            imported_tag_count=imported_tag_count,
            deleted_translation_items=deleted_translation_items,
            deleted_translation_backup_path=deleted_translation_backup_path,
        )

    async def translate_text(
        self,
        game_title: str,
        setting_overrides: SettingOverrides | None,
        custom_placeholder_rules_text: str | None,
        run_limits: TranslationRunLimits | None,
        callbacks: tuple[
            Callable[[int, int], None],
            Callable[[int], None],
            Callable[[str], None],
        ],
    ) -> TextTranslationSummary:
        """翻译指定游戏的正文。"""
        translation_cache = TranslationCache()
        async with await self.game_registry.open_game(game_title) as session:
            setting = self._load_runtime_setting(
                setting_overrides,
                source_language=session.source_language,
            )
            placeholder_rule_records: list[PlaceholderRuleRecord] | None = None
            if custom_placeholder_rules_text is None:
                placeholder_rule_records = await session.read_placeholder_rules()
            text_rules = self._load_text_rules(
                setting=setting,
                custom_placeholder_rules_text=custom_placeholder_rules_text,
                placeholder_rule_records=placeholder_rule_records,
                structured_placeholder_rule_records=await session.read_structured_placeholder_rules(),
            )
            return await self._translate_text_in_session(
                session=session,
                setting=setting,
                text_rules=text_rules,
                custom_placeholder_rules_supplied=custom_placeholder_rules_text is not None,
                translation_cache=translation_cache,
                run_limits=run_limits or TranslationRunLimits(),
                callbacks=callbacks,
            )

    async def _translate_text_from_warm_index(
        self,
        *,
        session: TargetGameSession,
        setting: Setting,
        text_rules: TextRules,
        translation_cache: TranslationCache,
        run_limits: TranslationRunLimits,
        callbacks: tuple[
            Callable[[int, int], None],
            Callable[[int], None],
            Callable[[str], None],
        ],
    ) -> TextTranslationSummary:
        """使用持久索引准备 `translate --max-items` 小批正文翻译。"""
        if run_limits.max_items is None:
            raise ValueError("warm index 翻译分支必须指定 max_items")
        if run_limits.max_items <= 0:
            raise ValueError("max_items 必须是正整数")

        set_progress, advance_progress, set_status = callbacks
        game_title = session.game_title
        set_status("检查持久文本范围索引")
        text_index_status = "used"
        text_index_rebuild_summary: JsonObject | None = None
        text_index_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        if text_index_invalidations:
            text_index_status = (
                "cold_rebuilt"
                if any(item.reason_key == "text_index_missing" for item in text_index_invalidations)
                else "stale_rebuilt"
            )
            text_index_rebuild_summary, rebuild_blocked_reason = await self._rebuild_text_index_for_translation(
                session=session,
                setting=setting,
                text_rules=text_rules,
                callbacks=callbacks,
            )
            if rebuild_blocked_reason is not None:
                blocked_reason = f"当前游戏持久文本范围索引自动重建失败: {rebuild_blocked_reason}"
                logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
                return TextTranslationSummary(
                    total_extracted_items=0,
                    pending_count=0,
                    deduplicated_count=0,
                    batch_count=0,
                    success_count=0,
                    error_count=0,
                    blocked_reason=blocked_reason,
                    total_pending_count=0,
                    text_index_status="rebuild_failed",
                    text_index_rebuild_summary=text_index_rebuild_summary,
                )
        metadata = await session.read_text_index_metadata()
        if metadata is None:
            blocked_reason = "当前游戏持久文本范围索引自动重建后仍不可读取，请重新运行 rebuild-text-index"
            logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
            return TextTranslationSummary(
                total_extracted_items=0,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
                blocked_reason=blocked_reason,
                total_pending_count=0,
                text_index_status="rebuild_failed",
                text_index_rebuild_summary=text_index_rebuild_summary,
            )

        workflow_gate_errors = await collect_text_index_external_rule_gate_errors(
            session=session,
            metadata=metadata,
        )
        if workflow_gate_errors:
            blocked_reason = format_workflow_gate_error(workflow_gate_errors)
            logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
            return TextTranslationSummary(
                total_extracted_items=metadata.item_count,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
                blocked_reason=blocked_reason,
                total_pending_count=0,
                text_index_status="rebuild_failed" if text_index_rebuild_summary is not None else text_index_status,
                text_index_rebuild_summary=text_index_rebuild_summary,
            )

        total_extracted_items = metadata.item_count
        total_pending_count = await session.count_pending_text_index_items()
        pending_index_items = await session.read_pending_text_index_items(limit=run_limits.max_items)
        pending_translation_data_map = text_index_items_to_translation_data_map(pending_index_items)
        pending_count = count_translation_items(pending_translation_data_map)
        set_progress(0, pending_count)

        if total_extracted_items == 0:
            blocked_reason = "没有提取到任何可翻译正文"
            logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
            return TextTranslationSummary(
                total_extracted_items=0,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
                blocked_reason=blocked_reason,
                total_pending_count=0,
                text_index_status=text_index_status,
                text_index_rebuild_summary=text_index_rebuild_summary,
            )
        if total_pending_count == 0:
            logger.info(f"[tag.skip]正文译文已全部存在，跳过翻译[/tag.skip] 游戏 [tag.count]{game_title}[/tag.count]")
            set_progress(total_extracted_items, total_extracted_items)
            return TextTranslationSummary(
                total_extracted_items=total_extracted_items,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
                total_pending_count=0,
                text_index_status=text_index_status,
                text_index_rebuild_summary=text_index_rebuild_summary,
            )

        terminology_prompt_index = await self._load_terminology_prompt_index(session=session)
        deduplicated_translation_data_map = deduplicate_translation_data(
            translation_data_map=pending_translation_data_map,
            translation_cache=translation_cache,
        )
        deduplicated_count = count_translation_items(deduplicated_translation_data_map)
        batches = build_translation_batches(
            translation_data_map=deduplicated_translation_data_map,
            setting=setting,
            text_rules=text_rules,
            terminology_prompt_index=terminology_prompt_index,
        )
        if run_limits.max_batches is not None:
            batches = batches[: run_limits.max_batches]
        deduplicated_count = sum(len(batch.items) for batch in batches)
        return await self._run_prepared_translation_batches(
            session=session,
            setting=setting,
            text_rules=text_rules,
            translation_cache=translation_cache,
            run_limits=run_limits,
            total_extracted_items=total_extracted_items,
            total_pending_count=total_pending_count,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batches=batches,
            set_status=set_status,
            advance_progress=advance_progress,
            text_index_status=text_index_status,
            text_index_rebuild_summary=text_index_rebuild_summary,
        )

    async def _run_prepared_translation_batches(
        self,
        *,
        session: TargetGameSession,
        setting: Setting,
        text_rules: TextRules,
        translation_cache: TranslationCache,
        run_limits: TranslationRunLimits,
        total_extracted_items: int,
        total_pending_count: int | None,
        pending_count: int,
        deduplicated_count: int,
        batches: list[TranslationBatch],
        set_status: Callable[[str], None],
        advance_progress: Callable[[int], None],
        text_index_status: str = "",
        text_index_rebuild_summary: JsonObject | None = None,
    ) -> TextTranslationSummary:
        """执行已经构建好的正文翻译批次，并维护翻译运行记录。"""
        game_title = session.game_title
        if not batches:
            blocked_reason = "相同原文合并后，没有可送入模型的批次"
            logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
            return TextTranslationSummary(
                total_extracted_items=total_extracted_items,
                pending_count=pending_count,
                deduplicated_count=deduplicated_count,
                batch_count=0,
                success_count=0,
                error_count=0,
                blocked_reason=blocked_reason,
                total_pending_count=total_pending_count,
                text_index_status=text_index_status,
                text_index_rebuild_summary=text_index_rebuild_summary,
            )

        run_record = await session.start_translation_run(
            total_extracted=total_extracted_items,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batch_count=len(batches),
        )
        set_status(f"还没成功保存译文 {pending_count} 条，相同原文合并后 {deduplicated_count} 条，批次 {len(batches)} 个")
        logger.info(f"[tag.phase]正文翻译开始[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 提取 [tag.count]{total_extracted_items}[/tag.count] 条，还没成功保存译文 [tag.count]{pending_count}[/tag.count] 条，相同原文合并后 [tag.count]{deduplicated_count}[/tag.count] 条，批次 [tag.count]{len(batches)}[/tag.count] 个")
        source_residual_rule_set = SourceResidualRuleSet.from_records(
            await session.read_source_residual_rules()
        )
        text_translation = TextTranslation(
            setting=setting,
            text_rules=text_rules,
            source_residual_rule_set=source_residual_rule_set,
        )
        try:
            success_count, error_count = await self._run_text_translation_batches(
                text_translation=text_translation,
                session=session,
                batches=batches,
                run_record=run_record,
                advance_progress=advance_progress,
                translation_cache=translation_cache,
                time_limit_seconds=run_limits.time_limit_seconds,
                stop_on_error_rate=run_limits.stop_on_error_rate,
            )
            finished_run = run_record.model_copy(
                update={
                    "status": "completed" if error_count == 0 else "blocked",
                    "success_count": success_count,
                    "quality_error_count": error_count,
                    "finished_at": current_timestamp_text(),
                    "stop_reason": "" if error_count == 0 else "存在模型翻了但项目检查没通过的译文",
                    "last_error": "" if error_count == 0 else "quality_errors",
                }
            )
            await session.write_translation_run(finished_run)
        except TranslationRunInterrupted as error:
            llm_failure_count = 0
            if error.llm_failure is not None:
                await session.write_llm_failure(
                    build_llm_failure_record(
                        run_id=run_record.run_id,
                        failure=error.llm_failure,
                    )
                )
                llm_failure_count = 1
            interrupted_run = run_record.model_copy(
                update={
                    "status": "blocked",
                    "success_count": error.success_count,
                    "quality_error_count": error.quality_error_count,
                    "llm_failure_count": llm_failure_count,
                    "finished_at": current_timestamp_text(),
                    "stop_reason": error.reason,
                    "last_error": str(error),
                }
            )
            await session.write_translation_run(interrupted_run)
            return TextTranslationSummary(
                total_extracted_items=total_extracted_items,
                pending_count=pending_count,
                deduplicated_count=deduplicated_count,
                batch_count=len(batches),
                success_count=error.success_count,
                error_count=error.quality_error_count,
                llm_failure_count=llm_failure_count,
                run_id=run_record.run_id,
                blocked_reason=error.reason,
                total_pending_count=total_pending_count,
                text_index_status=text_index_status,
                text_index_rebuild_summary=text_index_rebuild_summary,
            )
        return TextTranslationSummary(
            total_extracted_items=total_extracted_items,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batch_count=len(batches),
            success_count=success_count,
            error_count=error_count,
            run_id=run_record.run_id,
            total_pending_count=total_pending_count,
            text_index_status=text_index_status,
            text_index_rebuild_summary=text_index_rebuild_summary,
        )

    async def _translate_text_in_session(
        self,
        *,
        session: TargetGameSession,
        setting: Setting,
        text_rules: TextRules,
        custom_placeholder_rules_supplied: bool,
        translation_cache: TranslationCache,
        run_limits: TranslationRunLimits,
        callbacks: tuple[
            Callable[[int, int], None],
            Callable[[int], None],
            Callable[[str], None],
        ],
    ) -> TextTranslationSummary:
        """在单游戏数据库会话中翻译正文。"""
        set_progress, advance_progress, set_status = callbacks
        game_title = session.game_title
        if run_limits.max_items is not None:
            return await self._translate_text_from_warm_index(
                session=session,
                setting=setting,
                text_rules=text_rules,
                translation_cache=translation_cache,
                run_limits=run_limits,
                callbacks=callbacks,
            )
        game_data = await self._load_session_game_data(session)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await assert_workflow_gate_passed(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
            scope=scope,
        )
        terminology_prompt_index = await self._load_terminology_prompt_index(
            session=session,
            game_data=game_data,
        )
        translation_data_map = scope.translation_data_map

        total_extracted_items = count_translation_items(translation_data_map)
        translated_paths = await session.read_translation_location_paths()
        pending_translation_data_map = filter_pending_translation_data(
            translation_data_map=translation_data_map,
            translated_paths=translated_paths,
        )
        pending_translation_data_map = limit_translation_data(
            translation_data_map=pending_translation_data_map,
            max_items=run_limits.max_items,
        )
        pending_count = count_translation_items(pending_translation_data_map)
        set_progress(0, pending_count)

        if total_extracted_items == 0:
            blocked_reason = "没有提取到任何可翻译正文"
            logger.warning(f"[tag.warning]{blocked_reason}[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
            return TextTranslationSummary(
                total_extracted_items=0,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
                blocked_reason=blocked_reason,
            )

        if pending_count == 0:
            logger.info(f"[tag.skip]正文译文已全部存在，跳过翻译[/tag.skip] 游戏 [tag.count]{game_title}[/tag.count]")
            set_progress(total_extracted_items, total_extracted_items)
            return TextTranslationSummary(
                total_extracted_items=total_extracted_items,
                pending_count=0,
                deduplicated_count=0,
                batch_count=0,
                success_count=0,
                error_count=0,
            )

        deduplicated_translation_data_map = deduplicate_translation_data(
            translation_data_map=pending_translation_data_map,
            translation_cache=translation_cache,
        )
        deduplicated_count = count_translation_items(deduplicated_translation_data_map)
        batches = build_translation_batches(
            translation_data_map=deduplicated_translation_data_map,
            setting=setting,
            text_rules=text_rules,
            terminology_prompt_index=terminology_prompt_index,
        )
        if run_limits.max_batches is not None:
            batches = batches[: run_limits.max_batches]
        deduplicated_count = sum(len(batch.items) for batch in batches)
        return await self._run_prepared_translation_batches(
            session=session,
            setting=setting,
            text_rules=text_rules,
            translation_cache=translation_cache,
            run_limits=run_limits,
            total_extracted_items=total_extracted_items,
            total_pending_count=pending_count,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batches=batches,
            set_status=set_status,
            advance_progress=advance_progress,
        )

    async def write_back(
        self,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
        force_full_restore: bool = False,
    ) -> WriteBackSummary:
        """把数据库中的有效译文回写到游戏目录。"""
        if force_full_restore:
            return await self._rebuild_active_runtime_with_native_plan(
                game_title=game_title,
                callbacks=callbacks,
                setting_overrides=setting_overrides,
                confirm_font_overwrite=confirm_font_overwrite,
            )
        return await self._write_back_with_native_fast_gate(
            game_title=game_title,
            callbacks=callbacks,
            setting_overrides=setting_overrides,
            confirm_font_overwrite=confirm_font_overwrite,
        )

    async def _write_back_with_native_fast_gate(
        self,
        *,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting_overrides: SettingOverrides | None,
        confirm_font_overwrite: bool,
    ) -> WriteBackSummary:
        """使用 Rust 质检和写回计划执行普通写回。"""
        async with await self.game_registry.open_game(game_title) as session:
            set_progress, _advance_progress, set_status = _unpack_write_progress_callbacks(callbacks)
            set_progress(0, 1)
            set_status("执行写入前检查")
            prepared = await self._prepare_write_operation(
                session=session,
                setting_overrides=setting_overrides,
                mode="write_back",
                require_complete_translation=True,
            )
            if not prepared.translated_items and not await session.read_terminology_registry():
                logger.warning(f"[tag.warning]当前没有可回写译文，也没有已导入术语表[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
                return WriteBackSummary(
                    data_item_count=0,
                    plugin_item_count=0,
                    terminology_written_count=0,
                    target_font_name=None,
                    source_font_count=0,
                    replaced_font_reference_count=0,
                    font_copied=False,
                )
            return await self.write_runtime_files_with_native_plan(
                session=session,
                game_title=game_title,
                callbacks=callbacks,
                setting=prepared.setting,
                text_rules=prepared.text_rules,
                mode="write_back",
                writable_location_paths=prepared.writable_location_paths,
                confirm_font_overwrite=confirm_font_overwrite,
                success_phase="游戏文本回写完成",
                pre_write_check_ms=prepared.pre_write_check_ms,
            )

    async def _prepare_write_operation(
        self,
        *,
        session: TargetGameSession,
        setting_overrides: SettingOverrides | None,
        mode: WriteRuntimeMode,
        require_complete_translation: bool,
    ) -> PreparedWriteOperation:
        """为写文件操作统一加载数据、规则、文本范围和质量门禁。"""
        started = time.perf_counter()
        game_data = await self._load_session_game_data(
            session,
            include_plugin_source_files=True,
        )
        setting = self._load_setting(
            setting_overrides=setting_overrides,
            source_language=session.source_language,
        )
        text_rules = self._load_text_rules(
            setting=setting,
            placeholder_rule_records=await session.read_placeholder_rules(),
            structured_placeholder_rule_records=await session.read_structured_placeholder_rules(),
        )
        translated_items = await session.read_translated_items()
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            translated_items=translated_items,
            include_write_probe=False,
        )
        await assert_workflow_gate_passed(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            translated_items=translated_items,
            scope=scope,
        )
        await assert_write_back_quality_passed(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            translated_items=translated_items,
            require_complete_translation=require_complete_translation,
            scope=scope,
            include_native_checks=False,
        )
        writable_items = await self._filter_writable_translation_items(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            translated_items=translated_items,
            scope=scope,
        )
        if mode == "write_terminology" and await session.read_terminology_registry() is None:
            raise WriteBackGateError("当前游戏数据库中没有已导入术语表，请先执行 import-terminology")
        return PreparedWriteOperation(
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            translated_items=writable_items,
            writable_location_paths=sorted(item.location_path for item in writable_items),
            scope=scope,
            pre_write_check_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _assert_latest_translation_run_has_no_failures(
        self,
        session: TargetGameSession,
    ) -> None:
        """保留写回前对最新翻译运行失败状态的直接拦截语义。"""
        _ = self
        latest_run = await session.read_latest_translation_run()
        if latest_run is None:
            return
        quality_error_count = await session.count_translation_quality_errors(latest_run.run_id)
        if quality_error_count:
            raise RuntimeError(f"写进游戏文件前检查没通过：最新翻译运行有 {quality_error_count} 条模型翻了但项目检查没通过的译文")
        llm_failures = await session.read_llm_failures(latest_run.run_id)
        if llm_failures:
            raise RuntimeError(f"写进游戏文件前检查没通过：最新翻译运行存在 {len(llm_failures)} 条模型运行故障")

    async def rebuild_active_runtime(
        self,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> WriteBackSummary:
        """从可信源快照和当前数据库缓存重建游戏运行文件。"""
        return await self._rebuild_active_runtime_with_native_plan(
            game_title=game_title,
            callbacks=callbacks,
            setting_overrides=setting_overrides,
            confirm_font_overwrite=confirm_font_overwrite,
        )

    async def _rebuild_active_runtime_with_native_plan(
        self,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting_overrides: SettingOverrides | None,
        confirm_font_overwrite: bool,
    ) -> WriteBackSummary:
        """使用 Rust 热路径从可信源快照重建当前运行文件。"""
        async with await self.game_registry.open_game(game_title) as session:
            set_progress, _advance_progress, set_status = _unpack_write_progress_callbacks(callbacks)
            set_progress(0, 1)
            set_status("执行写入前检查")
            prepared = await self._prepare_write_operation(
                session=session,
                setting_overrides=setting_overrides,
                mode="rebuild_active_runtime",
                require_complete_translation=True,
            )
            return await self.write_runtime_files_with_native_plan(
                session=session,
                game_title=game_title,
                callbacks=callbacks,
                setting=prepared.setting,
                text_rules=prepared.text_rules,
                mode="rebuild_active_runtime",
                writable_location_paths=prepared.writable_location_paths,
                confirm_font_overwrite=confirm_font_overwrite,
                success_phase="游戏运行文件重建完成",
                pre_write_check_ms=prepared.pre_write_check_ms,
            )

    async def write_runtime_files_with_native_plan(
        self,
        *,
        session: TargetGameSession,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting: Setting,
        text_rules: TextRules,
        mode: WriteRuntimeMode,
        writable_location_paths: list[str],
        confirm_font_overwrite: bool,
        success_phase: str,
        pre_write_check_ms: int = 0,
    ) -> WriteBackSummary:
        """执行 Rust 写回计划，并保留 Python 侧事务替换协议。"""
        set_progress, advance_progress, set_status = _unpack_write_progress_callbacks(callbacks)
        set_status("准备 Rust 写回计划输入")
        setting_payload, source_font_path, source_font_names = build_native_write_back_setting_payload(
            setting=setting,
            text_rules=text_rules,
            content_root=session.content_root,
            confirm_font_overwrite=confirm_font_overwrite,
            writable_location_paths=writable_location_paths,
        )
        with tempfile.TemporaryDirectory(prefix="att_mz_native_plan_") as content_output_dir_text:
            content_output_dir = Path(content_output_dir_text)
            set_status("生成 Rust 写回计划")
            plan = build_native_write_back_plan(
                game_path=session.game_path,
                content_root=session.content_root,
                db_path=session.db_path,
                mode=mode,
                confirm_font_overwrite=confirm_font_overwrite,
                setting_payload=setting_payload,
                content_output_dir=content_output_dir,
            )
            total_count = max(plan.summary.data_item_count + plan.summary.plugin_item_count, 1)
            set_progress(0, total_count)
            font_records = list(plan.font_replacement_records)
            css_replaced_count = 0
            file_replacement_started = time.perf_counter()
            set_status("替换游戏运行文件")
            if source_font_path is not None:
                font_dir = session.content_root / FONTS_DIRECTORY_NAME
                copy_replacement_font(source_font_path=source_font_path, font_dir=font_dir)
                css_replaced_count, css_records = replace_gamefont_css_references(
                    font_dir=font_dir,
                    replacement_font_name=source_font_path.name,
                )
                font_records.extend(css_records)
                await session.replace_font_replacement_records(font_records)
            elif setting.write_back.replacement_font_path is not None:
                logger.info(f"[tag.skip]未确认覆盖字体，已跳过字体替换[/tag.skip] 游戏 [tag.count]{game_title}[/tag.count]")

            write_planned_text_file_sources(
                files=[
                    (file.target_path, file.content, file.content_path)
                    for file in plan.files
                ],
                rollback_dir_parent=session.content_root,
            )
            file_replacement_ms = int((time.perf_counter() - file_replacement_started) * 1000)

        set_status("保存写入诊断映射")
        await session.replace_plugin_source_runtime_write_maps(plan.plugin_source_runtime_write_maps)
        nonstandard_data_rule_records = await session.read_nonstandard_data_text_rules()
        post_write_audit_started = time.perf_counter()
        runtime_write_map_records = plan.plugin_source_runtime_write_maps
        if runtime_write_map_records or nonstandard_data_rule_records:
            set_status("审计写入后的当前运行文件")
            plugin_source_audit: ActiveRuntimePluginSourceAudit | None = None
            if runtime_write_map_records:
                active_runtime_game_data = await load_active_runtime_game_data(
                    session.game_path,
                    include_plugin_source_files=True,
                )
                plugin_source_audit, refreshed_scan_cache = audit_active_runtime_plugin_source_with_scan_cache(
                    game_data=active_runtime_game_data,
                    text_rules=text_rules,
                    cache_records=await session.read_plugin_source_runtime_scan_cache(),
                    created_at=current_timestamp_text(),
                    runtime_write_map_records=runtime_write_map_records,
                    audit_text_issues=True,
                    text_issue_scope_keys=frozenset(
                        (record.runtime_file_name, record.runtime_selector)
                        for record in runtime_write_map_records
                    ),
                )
                await session.replace_plugin_source_runtime_scan_cache(refreshed_scan_cache)
            self._assert_post_write_active_runtime_audit_passed(
                plugin_source_audit=plugin_source_audit,
                game_layout=resolve_game_layout(session.game_path) if nonstandard_data_rule_records else None,
                text_rules=text_rules,
                runtime_write_map_records=runtime_write_map_records,
                nonstandard_data_rule_records=nonstandard_data_rule_records,
            )
        else:
            set_status("跳过写入后的当前运行文件审计")
        post_write_audit_ms = int((time.perf_counter() - post_write_audit_started) * 1000)
        advance_progress(total_count)

        replaced_font_reference_count = plan.summary.replaced_font_reference_count + css_replaced_count
        source_font_count = len(source_font_names) if source_font_path is not None else plan.summary.source_font_count
        if plan.summary.target_font_name is not None:
            logger.info(f"[tag.phase]字体引用已同步[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 目标字体 [tag.path]{plan.summary.target_font_name}[/tag.path] 原字体 [tag.count]{source_font_count}[/tag.count] 个，替换引用 [tag.count]{replaced_font_reference_count}[/tag.count] 处")
        timing_text = "，".join(f"{name} {value}ms" for name, value in plan.timings_ms.items())
        logger.info(f"[tag.phase]写文件分段耗时[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 模式 [tag.count]{mode}[/tag.count] 写入前检查 [tag.count]{pre_write_check_ms}[/tag.count]ms，Rust 计划 {timing_text}，文件替换 [tag.count]{file_replacement_ms}[/tag.count]ms，写后审计 [tag.count]{post_write_audit_ms}[/tag.count]ms")
        logger.info(f"[tag.phase]Rust 写回计划完成[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 模式 [tag.count]{mode}[/tag.count] 写入文件 [tag.count]{plan.summary.planned_file_count}[/tag.count] 个，跳过 [tag.count]{plan.summary.skipped_file_count}[/tag.count] 个，插件源码源 AST 扫描 [tag.count]{plan.summary.plugin_source_ast_source_scan_file_count}[/tag.count] 个，写后 AST 验证 [tag.count]{plan.summary.plugin_source_ast_runtime_scan_file_count}[/tag.count] 个")
        logger.success(f"[tag.success]{success_phase}[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] data 文本 [tag.count]{plan.summary.data_item_count}[/tag.count] 条，插件文本 [tag.count]{plan.summary.plugin_item_count}[/tag.count] 条，术语 [tag.count]{plan.summary.terminology_written_count}[/tag.count] 条")
        return WriteBackSummary(
            data_item_count=plan.summary.data_item_count,
            plugin_item_count=plan.summary.plugin_item_count,
            terminology_written_count=plan.summary.terminology_written_count,
            target_font_name=plan.summary.target_font_name,
            source_font_count=source_font_count,
            replaced_font_reference_count=replaced_font_reference_count,
            font_copied=plan.summary.font_copied,
            planned_file_count=plan.summary.planned_file_count,
            skipped_file_count=plan.summary.skipped_file_count,
            plugin_source_ast_source_scan_file_count=plan.summary.plugin_source_ast_source_scan_file_count,
            plugin_source_ast_runtime_scan_file_count=plan.summary.plugin_source_ast_runtime_scan_file_count,
            plugin_source_runtime_map_count=plan.summary.plugin_source_runtime_map_count,
            pre_write_check_ms=pre_write_check_ms,
            rust_plan_ms=plan.timings_ms["total"],
            file_replacement_ms=file_replacement_ms,
            post_write_audit_ms=post_write_audit_ms,
        )

    def _assert_post_write_active_runtime_audit_passed(
        self,
        *,
        plugin_source_audit: ActiveRuntimePluginSourceAudit | None,
        game_layout: GameLayout | None,
        text_rules: TextRules,
        runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord],
        nonstandard_data_rule_records: list[NonstandardDataTextRuleRecord],
    ) -> None:
        """写入后审计当前运行插件源码和受管理非标准 data 文件。"""
        if runtime_write_map_records:
            if plugin_source_audit is None:
                raise RuntimeError("写入后插件源码审计缺少当前运行文件视图")
            blocking_issues = tuple(issue for issue in plugin_source_audit.issues if issue.blocking)
            if blocking_issues:
                counts = Counter(issue.code for issue in blocking_issues)
                summary_parts: list[str] = []
                for label, code in (
                    ("读取失败", "active_runtime_read_error"),
                    ("JS 语法错误", "active_runtime_syntax_error"),
                    ("源文残留", "active_runtime_source_residual"),
                    ("控制符风险", "active_runtime_placeholder_risk"),
                ):
                    count = counts.get(code, 0)
                    if count > 0:
                        summary_parts.append(f"{label} {count} 条")
                first_issue = blocking_issues[0]
                detail = first_issue.syntax_error or first_issue.read_error or first_issue.fragment
                detail_text = f"；{detail}" if detail else ""
                summary_text = (
                    "、".join(summary_parts)
                    if summary_parts
                    else f"{len(plugin_source_audit.issues)} 条问题"
                )
                message = (
                    f"写入后当前运行文件审计未通过：{summary_text}。"
                    f"首个问题：{first_issue.message}（文件 {first_issue.file_name}{detail_text}）"
                )
                raise WriteBackGateError(message)
        if nonstandard_data_rule_records:
            if game_layout is None:
                raise RuntimeError("写入后非标准 data 审计缺少当前运行文件布局")
            nonstandard_data_audit = audit_active_runtime_nonstandard_data(
                layout=game_layout,
                rule_records=nonstandard_data_rule_records,
                text_rules=text_rules,
            )
            if nonstandard_data_audit.issues:
                first_issue = nonstandard_data_audit.issues[0]
                detail = first_issue.read_error or first_issue.fragment
                detail_text = f"；{detail}" if detail else ""
                message = (
                    f"写入后当前运行文件审计未通过：非标准 data 文件问题 {len(nonstandard_data_audit.issues)} 条。"
                    f"首个问题：{first_issue.message}（文件 {first_issue.file_name}{detail_text}）"
                )
                raise WriteBackGateError(message)
        return

    async def export_terminology(
        self,
        game_title: str,
        output_dir: Path,
    ) -> TerminologyExportSummary:
        """导出术语表工程文件。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
            text_rules = await self._load_session_profile_text_rules(session)
            summary = await export_terminology_artifacts(
                game_data=game_data,
                output_dir=output_dir,
                mv_virtual_namebox_rule_records=mv_virtual_namebox_rules,
                text_rules=text_rules,
            )
            logger.success(f"[tag.success]术语表工程导出完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 字段译名表 [tag.path]{summary.field_terms_path}[/tag.path] 正文术语表 [tag.path]{summary.glossary_path}[/tag.path] 上下文目录 [tag.path]{summary.contexts_dir}[/tag.path]")
            return summary

    async def import_terminology(
        self,
        game_title: str,
        input_path: Path,
        glossary_input_path: Path,
    ) -> TerminologyImportSummary:
        """把外部 Agent 填写后的字段译名表和正文术语表导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            registry = await load_terminology_registry(field_terms_path=input_path)
            glossary = await load_terminology_glossary(glossary_path=glossary_input_path)
            mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
            text_rules = await self._load_session_profile_text_rules(session)
            expected_registry, _speaker_contexts, _database_contexts = TerminologyExtraction(
                game_data=game_data,
                mv_virtual_namebox_rule_records=mv_virtual_namebox_rules,
                text_rules=text_rules,
            ).extract_registry_and_contexts()
            validate_terminology_registry_shape(
                imported_registry=registry,
                expected_registry=expected_registry,
            )
            validate_terminology_bundle(registry=registry, glossary=glossary)
            await session.replace_terminology_bundle(registry=registry, glossary=glossary)
        imported_count = registry.total_entry_count()
        filled_count = registry.filled_entry_count()
        glossary_term_count = glossary.term_count()
        logger.success(f"[tag.success]术语表导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 字段条目 [tag.count]{imported_count}[/tag.count] 条，已填写 [tag.count]{filled_count}[/tag.count] 条，正文术语 [tag.count]{glossary_term_count}[/tag.count] 条")
        return TerminologyImportSummary(
            imported_entry_count=imported_count,
            filled_entry_count=filled_count,
            glossary_term_count=glossary_term_count,
        )

    async def write_terminology(
        self,
        game_title: str,
        callbacks: WriteProgressCallbacks,
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> TerminologyWriteSummary:
        """根据数据库中的术语表直接写回稳定名词。"""
        async with await self.game_registry.open_game(game_title) as session:
            _set_progress, _advance_progress, set_status = _unpack_write_progress_callbacks(callbacks)
            set_status("执行写入前检查")
            prepared = await self._prepare_write_operation(
                session=session,
                setting_overrides=setting_overrides,
                mode="write_terminology",
                require_complete_translation=False,
            )
            summary = await self.write_runtime_files_with_native_plan(
                session=session,
                game_title=game_title,
                callbacks=callbacks,
                setting=prepared.setting,
                text_rules=prepared.text_rules,
                mode="write_terminology",
                writable_location_paths=prepared.writable_location_paths,
                confirm_font_overwrite=confirm_font_overwrite,
                success_phase="术语写回完成",
                pre_write_check_ms=prepared.pre_write_check_ms,
            )
            return TerminologyWriteSummary(
                written_count=summary.terminology_written_count,
                preserved_translation_count=len(prepared.translated_items),
            )

    async def restore_font_replacement(
        self,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
    ) -> FontRestoreSummary:
        """按原始备份对比还原游戏数据中的字体引用。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = self._load_setting(
                setting_overrides=setting_overrides,
                source_language=session.source_language,
            )
            game_data = await self._load_session_game_data(session)
            records = await session.read_font_replacement_records()
            target_font_names = collect_replacement_font_names(
                replacement_font_path=setting.write_back.replacement_font_path,
                records=records,
            )
            if not target_font_names:
                logger.warning(f"[tag.warning]没有候选覆盖字体名称，无法判断需要还原哪个新字体引用[/tag.warning] 游戏 [tag.count]{game_title}[/tag.count]")
                return FontRestoreSummary(
                    restored_field_count=0,
                    restored_reference_count=0,
                    target_font_name=None,
                )

            restore_summary = restore_font_references_from_origin_backups(
                game_data=game_data,
                replacement_font_names=target_font_names,
            )
            if records:
                _ = await session.clear_font_replacement_records()
            target_font_name = "、".join(restore_summary.target_font_names)
            logger.success(f"[tag.success]字体引用还原完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 还原字段 [tag.count]{restore_summary.restored_field_count}[/tag.count] 个，引用 [tag.count]{restore_summary.restored_reference_count}[/tag.count] 处")
            return FontRestoreSummary(
                restored_field_count=restore_summary.restored_field_count,
                restored_reference_count=restore_summary.restored_reference_count,
                target_font_name=target_font_name,
            )

    async def _filter_writable_translation_items(
        self,
        *,
        session: TargetGameSession,
        game_data: GameData,
        text_rules: TextRules,
        translated_items: list[TranslationItem],
        scope: TextScopeResult | None = None,
    ) -> list[TranslationItem]:
        """仅保留当前提取规则仍能定位写回位置的译文条目。"""
        if scope is None:
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
                include_write_probe=False,
            )
        if scope.stale_plugin_rules:
            raise WriteBackGateError(
                f"存在 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导入插件规则后再写进游戏文件"
            )
        if scope.write_back_probe_error:
            raise WriteBackGateError(scope.write_back_probe_error)
        writable_paths = scope.writable_paths
        stale_paths = sorted(
            item.location_path
            for item in translated_items
            if item.location_path not in writable_paths
        )
        if stale_paths:
            samples = "、".join(stale_paths[:5])
            suffix = "" if len(stale_paths) <= 5 else f" 等 {len(stale_paths)} 条"
            raise WriteBackGateError(
                f"发现已保存译文不在当前可写文本范围内，不能继续写进游戏文件: {samples}{suffix}"
            )
        return list(translated_items)

    async def _load_terminology_prompt_index(
        self,
        *,
        session: TargetGameSession,
        game_data: GameData | None = None,
    ) -> TerminologyPromptIndex | None:
        """读取数据库正文术语表，并转换为正文提示词索引。"""
        registry = await session.read_terminology_registry()
        glossary = await session.read_terminology_glossary()
        if glossary is None:
            raise RuntimeError("当前游戏尚未导入正文术语表，检查没通过，不能继续")
        if registry is None:
            raise RuntimeError("当前游戏尚未导入字段译名表，检查没通过，不能继续")
        validate_terminology_bundle(registry=registry, glossary=glossary)

        index = TerminologyPromptIndex.from_glossary(glossary, game_data=game_data)
        logger.info(f"[tag.phase]已加载正文术语表[/tag.phase] 游戏 [tag.count]{session.game_title}[/tag.count] 可注入译名 [tag.count]{len(index.entries)}[/tag.count] 条")
        return index

    @staticmethod
    def _should_refresh_plugin_translation_items(
        old_rule: PluginTextRuleRecord | None,
        new_rule: PluginTextRuleRecord,
    ) -> bool:
        """判断插件规则变化后是否需要清理失效插件译文。"""
        if old_rule is None:
            return False
        return (
            old_rule.plugin_hash != new_rule.plugin_hash
            or old_rule.path_templates != new_rule.path_templates
        )

    @staticmethod
    def _should_refresh_event_command_translation_items(
        old_rule: EventCommandTextRuleRecord | None,
        new_rule: EventCommandTextRuleRecord,
    ) -> bool:
        """判断事件指令规则变化后是否需要清理失效译文。"""
        if old_rule is None:
            return False
        return (
            old_rule.command_code != new_rule.command_code
            or old_rule.parameter_filters != new_rule.parameter_filters
            or old_rule.path_templates != new_rule.path_templates
        )

    @staticmethod
    def _should_refresh_note_tag_translation_items(
        old_rule: NoteTagTextRuleRecord | None,
        new_rule: NoteTagTextRuleRecord,
    ) -> bool:
        """判断 Note 标签规则变化后是否需要清理失效译文。"""
        if old_rule is None:
            return False
        return (
            old_rule.file_name != new_rule.file_name
            or old_rule.tag_names != new_rule.tag_names
        )

    @staticmethod
    def _event_command_rule_prefixes(
        *,
        game_data: GameData,
        rule_record: EventCommandTextRuleRecord,
    ) -> list[str]:
        """根据事件指令规则找出需要清理的正文路径前缀。"""
        prefixes: list[str] = []
        for path, _display_name, command in iter_all_commands(game_data):
            if command.code != rule_record.command_code:
                continue
            if not command_matches_filters(
                parameters=command.parameters,
                filters=rule_record.parameter_filters,
            ):
                continue
            prefixes.append("/".join(map(str, path)))
        return prefixes

    async def _run_text_translation_batches(
        self,
        *,
        text_translation: TextTranslation,
        session: TargetGameSession,
        batches: list[TranslationBatch],
        run_record: TranslationRunRecord,
        advance_progress: Callable[[int], None],
        translation_cache: TranslationCache,
        time_limit_seconds: int | None,
        stop_on_error_rate: float | None,
    ) -> tuple[int, int]:
        """启动正文翻译并并发消费成功/失败队列。"""
        game_title = session.game_title
        text_translation.start_translation(llm_handler=self.llm_handler, batches=batches)
        db_write_lock = asyncio.Lock()
        progress_state = TranslationProgressState()
        success_task = asyncio.create_task(
            self._consume_right_items(
                session=session,
                text_translation=text_translation,
                run_record=run_record,
                progress_state=progress_state,
                db_write_lock=db_write_lock,
                advance_progress=advance_progress,
                translation_cache=translation_cache,
            )
        )
        error_task = asyncio.create_task(
            self._consume_error_items(
                session=session,
                text_translation=text_translation,
                run_record=run_record,
                progress_state=progress_state,
                db_write_lock=db_write_lock,
                advance_progress=advance_progress,
                translation_cache=translation_cache,
                stop_on_error_rate=stop_on_error_rate,
            )
        )
        results: tuple[int | BaseException, int | BaseException]
        try:
            gather_task = asyncio.gather(success_task, error_task, return_exceptions=True)
            if time_limit_seconds is None:
                results = await gather_task
            else:
                results = await asyncio.wait_for(gather_task, timeout=time_limit_seconds)
        except asyncio.TimeoutError as error:
            raise TranslationRunInterrupted(
                reason=f"达到本轮翻译时间上限: {time_limit_seconds} 秒",
                success_count=progress_state.success_count,
                quality_error_count=progress_state.quality_error_count,
            ) from error
        finally:
            for task in (success_task, error_task):
                if not task.done():
                    _ = task.cancel()
            await text_translation.stop()
            _ = await asyncio.gather(success_task, error_task, return_exceptions=True)

        runner_error: Exception | None = None
        for result in results:
            if isinstance(result, Exception):
                runner_error = result
                break
        if runner_error is not None:
            if isinstance(runner_error, TranslationRunInterrupted):
                raise runner_error
            if isinstance(runner_error, LLMRequestFailure):
                raise TranslationRunInterrupted(
                    reason=f"模型请求失败: {runner_error.info.message}",
                    success_count=progress_state.success_count,
                    quality_error_count=progress_state.quality_error_count,
                    llm_failure=runner_error,
                ) from runner_error
            raise runner_error

        success_count = progress_state.success_count
        error_count = progress_state.quality_error_count
        logger.success(f"[tag.success]正文翻译结束[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 成功 [tag.count]{success_count}[/tag.count] 条，失败 [tag.count]{error_count}[/tag.count] 条")
        return success_count, error_count

    async def _consume_right_items(
        self,
        *,
        session: TargetGameSession,
        text_translation: TextTranslation,
        run_record: TranslationRunRecord,
        progress_state: TranslationProgressState,
        db_write_lock: asyncio.Lock,
        advance_progress: Callable[[int], None],
        translation_cache: TranslationCache,
    ) -> int:
        """消费正文翻译成功队列并写入主翻译表。"""
        game_title = session.game_title
        success_count = 0
        async for items in text_translation.iter_right_items():
            expanded_items = expand_cached_translation_items(items, translation_cache)
            async with db_write_lock:
                await session.write_translation_items(expanded_items)
                success_count += len(expanded_items)
                progress_state.success_count += len(expanded_items)
                await session.write_translation_run(
                    run_record.model_copy(update={"success_count": progress_state.success_count})
                )
            advance_progress(len(expanded_items))
            logger.success(f"[tag.success]已写入正文翻译结果[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] [tag.count]{len(expanded_items)}[/tag.count] 条")
        return success_count

    async def _consume_error_items(
        self,
        *,
        session: TargetGameSession,
        text_translation: TextTranslation,
        run_record: TranslationRunRecord,
        progress_state: TranslationProgressState,
        db_write_lock: asyncio.Lock,
        advance_progress: Callable[[int], None],
        translation_cache: TranslationCache,
        stop_on_error_rate: float | None,
    ) -> int:
        """消费没通过项目检查的译文队列并写入固定错误表。"""
        game_title = session.game_title
        error_count = 0
        async for error_items in text_translation.iter_error_items():
            expanded_error_items = expand_cached_error_items(error_items, translation_cache)
            async with db_write_lock:
                await session.write_translation_quality_errors(
                    run_record.run_id,
                    expanded_error_items,
                )
                error_count += len(expanded_error_items)
                progress_state.quality_error_count += len(expanded_error_items)
                await session.write_translation_run(
                    run_record.model_copy(
                        update={
                            "success_count": progress_state.success_count,
                            "quality_error_count": progress_state.quality_error_count,
                        }
                    )
                )
            advance_progress(len(expanded_error_items))
            logger.error(f"[tag.failure]已记录检查没通过的译文[/tag.failure] 游戏 [tag.count]{game_title}[/tag.count] [tag.count]{len(expanded_error_items)}[/tag.count] 条")
            if stop_on_error_rate is not None:
                processed_count = progress_state.success_count + progress_state.quality_error_count
                if processed_count > 0 and progress_state.quality_error_count / processed_count >= stop_on_error_rate:
                    raise TranslationRunInterrupted(
                        reason=f"检查没通过的译文比例达到停止阈值: {stop_on_error_rate}",
                        success_count=progress_state.success_count,
                        quality_error_count=progress_state.quality_error_count,
                    )
        return error_count


def validate_terminology_registry_shape(
    *,
    imported_registry: TerminologyRegistry,
    expected_registry: TerminologyRegistry,
) -> None:
    """校验导入术语表与当前游戏可提取术语完全一致。"""
    imported_map = imported_registry.as_category_map()
    expected_map = expected_registry.as_category_map()
    errors: list[str] = []
    for category, expected_entries in expected_map.items():
        imported_entries = imported_map[category]
        missing_terms = sorted(set(expected_entries) - set(imported_entries))
        extra_terms = sorted(set(imported_entries) - set(expected_entries))
        if missing_terms:
            errors.append(f"{category} 缺少 {len(missing_terms)} 个术语")
        if extra_terms:
            errors.append(f"{category} 多出 {len(extra_terms)} 个术语")
    if errors:
        raise ValueError("；".join(errors))


__all__: list[str] = [
    "EventCommandJsonExportSummary",
    "EventCommandRuleImportSummary",
    "FontRestoreSummary",
    "PluginJsonExportSummary",
    "PluginRuleImportSummary",
    "TerminologyImportSummary",
    "TerminologyWriteSummary",
    "TextTranslationSummary",
    "TranslationHandler",
    "TranslationProgressState",
    "TranslationRunInterrupted",
    "TranslationRunLimits",
    "WriteBackSummary",
]
