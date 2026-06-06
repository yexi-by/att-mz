"""Agent 工具箱 CoreAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentServiceContext,
    CustomPlaceholderRule,
    GameData,
    PluginTextRuleRecord,
    SourceResidualRuleRecord,
    StructuredPlaceholderRule,
    TargetGameSession,
    TextRules,
    TranslationData,
    TranslationItem,
    build_source_residual_rule_records_from_import,
    load_active_runtime_game_data,
    load_game_data_for_view,
    load_custom_placeholder_rules_text,
    load_setting,
    parse_source_residual_rule_import_text,
    read_fresh_plugin_text_rules,
)
from app.plugin_source_text import PluginSourceScan
from app.rmmz.game_file_view import GameFileView
from app.rmmz.source_snapshot import validate_source_snapshot_manifest
from app.text_index import (
    detect_text_index_invalidations,
    rebuild_text_index_native_storage,
    text_index_item_to_translation_item,
    text_index_items_to_translation_data_map,
)


class CoreAgentMixin:
    """承载 AgentToolkitService 的 CoreAgentMixin 命令族。"""

    async def _load_game_data_for_view(
        self: AgentServiceContext,
        session: TargetGameSession,
        *,
        source_view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        """按显式视图加载单游戏数据，并在翻译源视图绑定会话。"""
        game_data = await load_game_data_for_view(
            session.game_path,
            source_view=source_view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )
        if source_view == GameFileView.TRANSLATION_SOURCE:
            snapshot_records = await session.read_source_snapshot_records()
            if not snapshot_records:
                raise RuntimeError("当前游戏缺少可信源快照 manifest，请使用干净游戏目录重新执行 add-game")
            validate_source_snapshot_manifest(
                layout=game_data.layout,
                records=snapshot_records,
            )
            session.set_game_data(game_data)
        return game_data

    async def _load_translation_source_game_data(
        self: AgentServiceContext,
        session: TargetGameSession,
        *,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        """加载翻译源视图，完整原始备份存在时优先读取备份。"""
        return await self._load_game_data_for_view(
            session,
            source_view=GameFileView.TRANSLATION_SOURCE,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    async def _load_active_runtime_game_data(
        self: AgentServiceContext,
        session: TargetGameSession,
        *,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        """加载当前运行视图，不读取任何 origin 备份。"""
        return await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    async def _extract_active_translation_data_map(
        self: AgentServiceContext,
        *,
        session: TargetGameSession,
        game_data: GameData,
        text_rules: TextRules,
        plugin_source_scan: PluginSourceScan | None = None,
    ) -> dict[str, TranslationData]:
        """兼容旧内部调用点，从 Rust 持久索引读取当前正文条目。"""
        _ = (game_data, plugin_source_scan)
        return await self._read_active_translation_data_map_from_text_index(
            session=session,
            text_rules=text_rules,
        )

    async def _read_active_translation_data_map_from_text_index(
        self: AgentServiceContext,
        *,
        session: TargetGameSession,
        text_rules: TextRules,
    ) -> dict[str, TranslationData]:
        """读取当前持久文本索引；失效时用 Rust 原生入口重建。"""
        text_index_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        if text_index_invalidations:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            _ = await rebuild_text_index_native_storage(
                session=session,
                setting=setting,
                text_rules=text_rules,
                include_write_probe=False,
            )
        return text_index_items_to_translation_data_map(await session.read_text_index_items())

    async def _build_source_residual_rule_records(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> list[SourceResidualRuleRecord]:
        """解析并按当前索引事实校验源文残留例外规则。"""
        import_file = parse_source_residual_rule_import_text(rules_text)
        position_paths = sorted(import_file.position_rules)
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            active_items: list[TranslationItem] = []
            translated_items: list[TranslationItem] = []
            if position_paths:
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                structured_rules = await self._resolve_structured_rules(session=session)
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                text_index_invalidations = await detect_text_index_invalidations(
                    session=session,
                    text_rules=text_rules,
                )
                if text_index_invalidations:
                    rebuild_report = await self.rebuild_text_index(
                        game_title=game_title,
                        include_write_probe=False,
                    )
                    if rebuild_report.status == "error":
                        messages = "；".join(error.message for error in rebuild_report.errors)
                        if not messages:
                            messages = "文本范围索引重建失败"
                        raise RuntimeError(f"源文残留例外规则校验前无法建立文本范围索引: {messages}")
                index_records = await session.read_text_index_items_by_paths(position_paths)
                active_items = [text_index_item_to_translation_item(record) for record in index_records]
                translated_items = await session.read_translated_items_by_paths(position_paths)
        return build_source_residual_rule_records_from_import(
            import_file=import_file,
            active_items=active_items,
            translated_items=translated_items,
            ignore_case=setting.text_rules.source_residual_terms_ignore_case,
        )

    async def _read_fresh_plugin_text_rules(
        self: AgentServiceContext,
        *,
        session: TargetGameSession,
        game_data: GameData,
    ) -> tuple[list[PluginTextRuleRecord], int]:
        """读取仍匹配当前 `plugins.js` 的插件规则，并统计过期规则。"""
        fresh_rules, stale_rules = await read_fresh_plugin_text_rules(
            session=session,
            game_data=game_data,
        )
        return fresh_rules, len(stale_rules)

    async def _resolve_custom_rules(
        self: AgentServiceContext,
        *,
        session: TargetGameSession,
        custom_placeholder_rules_text: str | None,
    ) -> tuple[CustomPlaceholderRule, ...]:
        """按 CLI 覆盖优先级解析自定义占位符规则。"""
        if custom_placeholder_rules_text is not None:
            return load_custom_placeholder_rules_text(custom_placeholder_rules_text)
        records = await session.read_placeholder_rules()
        return tuple(
            CustomPlaceholderRule.create(
                pattern_text=record.pattern_text,
                placeholder_template=record.placeholder_template,
            )
            for record in records
        )

    async def _resolve_structured_rules(
        self: AgentServiceContext,
        *,
        session: TargetGameSession,
    ) -> tuple[StructuredPlaceholderRule, ...]:
        """读取当前游戏数据库中的结构化占位符规则。"""
        records = await session.read_structured_placeholder_rules()
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
