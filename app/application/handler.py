"""
核心 CLI 翻译编排模块。

本模块串起游戏注册、外部规则导入、正文翻译、已保存译文复用与游戏文件回写。
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Self

from app.application.file_writer import reset_writable_copies, write_game_files
from app.application.font_replacement import (
    apply_font_replacement,
    build_empty_font_replacement_summary,
    collect_replacement_font_names,
    restore_font_references_from_origin_backups,
)
from app.application.runtime import load_runtime_setting
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
from app.config import (
    SettingOverrides,
    load_custom_placeholder_rules_text,
)
from app.config.schemas import Setting
from app.language import DEFAULT_SOURCE_LANGUAGE, SourceLanguage
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
    apply_terminology_translations,
    export_terminology_artifacts,
    load_terminology_glossary,
    load_terminology_registry,
)
from app.note_tag_text import (
    NoteTagTextExtraction,
    build_note_tag_rule_records_from_import,
    export_note_tag_candidates_file,
    load_note_tag_rule_import_file,
)
from app.persistence import GameRegistry, TargetGameSession
from app.persistence.repository import current_timestamp_text
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    event_command_rule_scope_hash,
    note_tag_rule_scope_hash,
    plugin_rule_scope_hash,
)
from app.plugin_text import (
    build_plugin_rule_records_from_import,
    export_plugins_json_file,
    load_plugin_rule_import_file,
)
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
    EventCommandTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PLUGINS_FILE_NAME,
    PluginTextRuleRecord,
    TranslationItem,
    TranslationRunRecord,
)
from app.rmmz.control_codes import CustomPlaceholderRule
from app.llm import LLMHandler, LLMRequestFailure
from app.rmmz.text_rules import TextRules
from app.translation import TextTranslation, TranslationBatch, TranslationCache
from app.rmmz.loader import load_game_data, read_game_title, resolve_game_directory, resolve_game_layout
from app.observability.logging import logger
from app.rmmz.write_back import write_data_text
from app.plugin_text.write_back import write_plugin_text
from app.utils.config_loader_utils import load_setting
from app.source_residual import SourceResidualRuleSet
from app.text_scope import TextScopeService, collect_translation_data_paths


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
        source_language: SourceLanguage = DEFAULT_SOURCE_LANGUAGE,
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
        source_language: SourceLanguage = DEFAULT_SOURCE_LANGUAGE,
    ) -> Setting:
        """加载当前配置，不改动模型服务连接状态。"""
        return load_setting(overrides=setting_overrides, source_language=source_language)

    def _load_text_rules(
        self,
        setting: Setting,
        custom_placeholder_rules_text: str | None = None,
        placeholder_rule_records: list[PlaceholderRuleRecord] | None = None,
    ) -> TextRules:
        """加载文本过滤规则和自定义占位符规则。"""
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

        if custom_rules:
            logger.info(f"[tag.phase]已加载自定义占位符规则[/tag.phase] 来源 {source_label} 数量 [tag.count]{len(custom_rules)}[/tag.count] 条")
        elif custom_placeholder_rules_text is not None:
            logger.info("[tag.skip]CLI 指定的自定义占位符规则为空对象[/tag.skip]")
        return TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=custom_rules,
        )

    async def _load_session_game_data(self, session: TargetGameSession) -> GameData:
        """加载目标游戏数据并绑定到当前命令会话。"""
        game_data = await load_game_data(session.game_path)
        session.set_game_data(game_data)
        return session.require_game_data()

    async def resolve_game_title_by_path(self, game_path: str | Path) -> str:
        """根据已注册游戏目录解析可用于 CLI 的游戏标题。"""
        return await self.game_registry.resolve_registered_title_by_path(game_path)

    async def add_game(
        self,
        game_path: str | Path,
        source_language: SourceLanguage,
    ) -> str:
        """注册一个新的游戏。"""
        resolved_game_path = resolve_game_directory(game_path)
        layout = resolve_game_layout(resolved_game_path)
        game_title = read_game_title(resolved_game_path)
        _ = await load_game_data(resolved_game_path)
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
    ) -> PluginRuleImportSummary:
        """把外部插件规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            import_file = await load_plugin_rule_import_file(input_path)
            rule_records = build_plugin_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
            )
            old_rules = {
                rule.plugin_index: rule
                for rule in await session.read_plugin_text_rules()
            }
            deleted_translation_items = 0
            stale_prefixes: set[str] = set()
            for rule_record in rule_records:
                old_rule = old_rules.get(rule_record.plugin_index)
                if self._should_refresh_plugin_translation_items(old_rule, rule_record):
                    stale_prefixes.add(f"{PLUGINS_FILE_NAME}/{rule_record.plugin_index}/")
            new_plugin_indexes = {rule.plugin_index for rule in rule_records}
            for plugin_index in sorted(set(old_rules) - new_plugin_indexes):
                stale_prefixes.add(f"{PLUGINS_FILE_NAME}/{plugin_index}/")
            if stale_prefixes:
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
        return PluginRuleImportSummary(
            imported_plugin_count=len(rule_records),
            imported_rule_count=imported_rule_count,
            deleted_translation_items=deleted_translation_items,
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
    ) -> EventCommandRuleImportSummary:
        """把外部事件指令规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            import_file = await load_event_command_rule_import_file(input_path)
            rule_records = build_event_command_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
            )
            old_rules = {
                event_command_rule_key(rule): rule
                for rule in await session.read_event_command_text_rules()
            }
            deleted_translation_items = 0
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
                deleted_translation_items = await session.delete_translation_items_by_prefixes(
                    sorted(stale_prefixes),
                )
            await session.replace_event_command_text_rules(rule_records)
            if rule_records:
                await session.delete_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
                    scope_hash=event_command_rule_scope_hash(game_data),
                    reviewed_empty=True,
                )
        imported_path_rule_count = sum(len(record.path_templates) for record in rule_records)
        logger.success(f"[tag.success]事件指令规则导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 规则组 [tag.count]{len(rule_records)}[/tag.count] 个，路径规则 [tag.count]{imported_path_rule_count}[/tag.count] 条，清理失效译文 [tag.count]{deleted_translation_items}[/tag.count] 条")
        return EventCommandRuleImportSummary(
            imported_rule_group_count=len(rule_records),
            imported_path_rule_count=imported_path_rule_count,
            deleted_translation_items=deleted_translation_items,
        )

    async def import_note_tag_rules(
        self,
        game_title: str,
        input_path: Path,
    ) -> NoteTagRuleImportSummary:
        """把外部 Note 标签规则 JSON 导入当前游戏数据库。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = self._load_setting(source_language=session.source_language)
            game_data = await self._load_session_game_data(session)
            text_rules = self._load_text_rules(
                setting=setting,
                placeholder_rule_records=await session.read_placeholder_rules(),
            )
            import_file = await load_note_tag_rule_import_file(input_path)
            rule_records = build_note_tag_rule_records_from_import(
                game_data=game_data,
                import_file=import_file,
                text_rules=text_rules,
            )
            old_rules = {
                rule.file_name: rule
                for rule in await session.read_note_tag_text_rules()
            }
            old_note_paths = collect_translation_data_paths(
                NoteTagTextExtraction(
                    game_data=game_data,
                    rule_records=list(old_rules.values()),
                    text_rules=text_rules,
                ).extract_all_text()
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
            if stale_paths and (changed_rule_count or removed_rule_count):
                deleted_translation_items = await session.delete_translation_items_by_paths(stale_paths)
            await session.replace_note_tag_text_rules(rule_records)
            if rule_records:
                await session.delete_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                    scope_hash=note_tag_rule_scope_hash(game_data),
                    reviewed_empty=True,
                )
        imported_tag_count = sum(len(record.tag_names) for record in rule_records)
        logger.success(f"[tag.success]Note 标签规则导入完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 文件 [tag.count]{len(rule_records)}[/tag.count] 个，标签 [tag.count]{imported_tag_count}[/tag.count] 个，清理失效译文 [tag.count]{deleted_translation_items}[/tag.count] 条")
        return NoteTagRuleImportSummary(
            imported_file_count=len(rule_records),
            imported_tag_count=imported_tag_count,
            deleted_translation_items=deleted_translation_items,
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
            )
            return await self._translate_text_in_session(
                session=session,
                setting=setting,
                text_rules=text_rules,
                translation_cache=translation_cache,
                run_limits=run_limits or TranslationRunLimits(),
                callbacks=callbacks,
            )

    async def _translate_text_in_session(
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
        """在单游戏数据库会话中翻译正文。"""
        set_progress, advance_progress, set_status = callbacks
        game_title = session.game_title
        game_data = await self._load_session_game_data(session)
        terminology_prompt_index = await self._load_terminology_prompt_index(
            session=session,
            game_data=game_data,
        )

        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        translation_data_map = scope.translation_data_map
        if scope.stale_plugin_rules:
            raise RuntimeError(
                f"存在 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导入插件规则后再翻译"
            )
        if scope.write_back_probe_error:
            raise RuntimeError(scope.write_back_probe_error)
        if scope.unwritable_entries:
            raise RuntimeError(
                f"存在 {len(scope.unwritable_entries)} 条当前文本无法写进游戏文件，请先运行 audit-coverage 查看明细"
            )

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
            )
        return TextTranslationSummary(
            total_extracted_items=total_extracted_items,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batch_count=len(batches),
            success_count=success_count,
            error_count=error_count,
            run_id=run_record.run_id,
        )

    async def write_back(
        self,
        game_title: str,
        callbacks: tuple[Callable[[int, int], None], Callable[[int], None]],
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> WriteBackSummary:
        """把数据库中的有效译文回写到游戏目录。"""
        async with await self.game_registry.open_game(game_title) as session:
            set_progress, advance_progress = callbacks
            game_data = await self._load_session_game_data(session)
            setting = self._load_setting(
                setting_overrides=setting_overrides,
                source_language=session.source_language,
            )
            text_rules = self._load_text_rules(
                setting=setting,
                placeholder_rule_records=await session.read_placeholder_rules(),
            )
            translated_items = await session.read_translated_items()
            translated_items = await self._filter_writable_translation_items(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
            )
            terminology_registry = await session.read_terminology_registry()
            set_progress(0, len(translated_items))

            if not translated_items and terminology_registry is None:
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

            reset_writable_copies(game_data)
            data_item_count = sum(
                1 for item in translated_items if not item.location_path.startswith(f"{PLUGINS_FILE_NAME}/")
            )
            plugin_item_count = len(translated_items) - data_item_count
            if translated_items:
                write_data_text(
                    game_data,
                    translated_items,
                    text_rules=text_rules,
                    speaker_name_translations=(
                        terminology_registry.speaker_names if terminology_registry is not None else None
                    ),
                )
                if data_item_count:
                    advance_progress(data_item_count)
                write_plugin_text(game_data, translated_items)
                if plugin_item_count:
                    advance_progress(plugin_item_count)
            terminology_written_count = 0
            if terminology_registry is not None:
                terminology_written_count = apply_terminology_translations(game_data, terminology_registry)
            font_summary = build_empty_font_replacement_summary()
            if confirm_font_overwrite:
                font_summary = apply_font_replacement(
                    game_data=game_data,
                    game_root=session.game_path,
                    replacement_font_path=setting.write_back.replacement_font_path,
                )
                if font_summary.target_font_name is not None:
                    await session.replace_font_replacement_records(font_summary.records)
            elif setting.write_back.replacement_font_path is not None:
                logger.info(f"[tag.skip]未确认覆盖字体，已跳过字体替换[/tag.skip] 游戏 [tag.count]{game_title}[/tag.count]")

            write_game_files(game_data=game_data, game_root=session.game_path)
            if font_summary.target_font_name is not None:
                logger.info(f"[tag.phase]字体引用已同步[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 目标字体 [tag.path]{font_summary.target_font_name}[/tag.path] 原字体 [tag.count]{font_summary.source_font_count}[/tag.count] 个，替换引用 [tag.count]{font_summary.replaced_reference_count}[/tag.count] 处")
            logger.success(f"[tag.success]游戏文本回写完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] data 文本 [tag.count]{data_item_count}[/tag.count] 条，插件文本 [tag.count]{plugin_item_count}[/tag.count] 条，术语 [tag.count]{terminology_written_count}[/tag.count] 条")
            return WriteBackSummary(
                data_item_count=data_item_count,
                plugin_item_count=plugin_item_count,
                terminology_written_count=terminology_written_count,
                target_font_name=font_summary.target_font_name,
                source_font_count=font_summary.source_font_count,
                replaced_font_reference_count=font_summary.replaced_reference_count,
                font_copied=font_summary.copied,
            )

    async def export_terminology(
        self,
        game_title: str,
        output_dir: Path,
    ) -> TerminologyExportSummary:
        """导出术语表工程文件。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_session_game_data(session)
            summary = await export_terminology_artifacts(
                game_data=game_data,
                output_dir=output_dir,
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
            expected_registry, _speaker_contexts, _database_contexts = TerminologyExtraction(
                game_data=game_data,
            ).extract_registry_and_contexts()
            validate_terminology_registry_shape(
                imported_registry=registry,
                expected_registry=expected_registry,
            )
            await session.replace_terminology_registry(registry)
            await session.replace_terminology_glossary(glossary)
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
        callbacks: tuple[Callable[[int, int], None], Callable[[int], None]],
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> TerminologyWriteSummary:
        """根据数据库中的术语表直接写回稳定名词。"""
        async with await self.game_registry.open_game(game_title) as session:
            set_progress, advance_progress = callbacks
            game_data = await self._load_session_game_data(session)
            setting = self._load_setting(
                setting_overrides=setting_overrides,
                source_language=session.source_language,
            )
            text_rules = self._load_text_rules(
                setting=setting,
                placeholder_rule_records=await session.read_placeholder_rules(),
            )
            translated_items = await session.read_translated_items()
            translated_items = await self._filter_writable_translation_items(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
            )
            registry = await session.read_terminology_registry()
            if registry is None:
                raise RuntimeError("当前游戏数据库中没有已导入术语表，请先执行 import-terminology")

            reset_writable_copies(game_data)
            if translated_items:
                write_data_text(
                    game_data,
                    translated_items,
                    text_rules=text_rules,
                    speaker_name_translations=registry.speaker_names,
                )
                write_plugin_text(game_data, translated_items)

            written_count = apply_terminology_translations(game_data, registry)
            set_progress(0, max(written_count, 1))
            advance_progress(written_count)
            font_summary = build_empty_font_replacement_summary()
            if confirm_font_overwrite:
                font_summary = apply_font_replacement(
                    game_data=game_data,
                    game_root=session.game_path,
                    replacement_font_path=setting.write_back.replacement_font_path,
                )
                if font_summary.target_font_name is not None:
                    await session.replace_font_replacement_records(font_summary.records)
            elif setting.write_back.replacement_font_path is not None:
                logger.info(f"[tag.skip]未确认覆盖字体，已跳过字体替换[/tag.skip] 游戏 [tag.count]{game_title}[/tag.count]")
            write_game_files(game_data=game_data, game_root=session.game_path)
            if font_summary.target_font_name is not None:
                logger.info(f"[tag.phase]字体引用已同步[/tag.phase] 游戏 [tag.count]{game_title}[/tag.count] 目标字体 [tag.path]{font_summary.target_font_name}[/tag.path] 原字体 [tag.count]{font_summary.source_font_count}[/tag.count] 个，替换引用 [tag.count]{font_summary.replaced_reference_count}[/tag.count] 处")
            logger.success(f"[tag.success]术语写回完成[/tag.success] 游戏 [tag.count]{game_title}[/tag.count] 写回 [tag.count]{written_count}[/tag.count] 条，保留已有正文译文 [tag.count]{len(translated_items)}[/tag.count] 条")
            return TerminologyWriteSummary(written_count=written_count, preserved_translation_count=len(translated_items))

    async def restore_font_replacement(
        self,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
    ) -> FontRestoreSummary:
        """按原件留档对比还原游戏数据中的字体引用。"""
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
    ) -> list[TranslationItem]:
        """仅保留当前提取规则仍能定位写回位置的译文条目。"""
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            translated_items=translated_items,
        )
        if scope.stale_plugin_rules:
            raise RuntimeError(
                f"存在 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导入插件规则后再写进游戏文件"
            )
        if scope.write_back_probe_error:
            raise RuntimeError(scope.write_back_probe_error)
        writable_paths = scope.writable_paths
        stale_paths = sorted(
            item.location_path
            for item in translated_items
            if item.location_path not in writable_paths
        )
        if stale_paths:
            samples = "、".join(stale_paths[:5])
            suffix = "" if len(stale_paths) <= 5 else f" 等 {len(stale_paths)} 条"
            raise RuntimeError(
                f"发现已保存译文不在当前可写文本范围内，不能继续写进游戏文件: {samples}{suffix}"
            )
        return list(translated_items)

    async def _load_terminology_prompt_index(
        self,
        *,
        session: TargetGameSession,
        game_data: GameData,
    ) -> TerminologyPromptIndex | None:
        """读取数据库正文术语表，并转换为正文提示词索引。"""
        glossary = await session.read_terminology_glossary()
        if glossary is None:
            logger.info(f"[tag.skip]数据库没有已导入正文术语表，正文提示词不注入标准译名[/tag.skip] 游戏 [tag.count]{session.game_title}[/tag.count]")
            return None

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
