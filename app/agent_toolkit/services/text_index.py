"""Agent 工具箱文本范围索引子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import time

from app.application.flow_gate import collect_plugin_source_workflow_gate_errors
from app.rmmz.text_rules import JsonObject
from app.text_index import rebuild_text_index as rebuild_persistent_text_index

from .common import (
    AgentReport,
    AgentServiceContext,
    QualityProgressCallbacks,
    SettingOverrides,
    TextRules,
    TextScopeService,
    _noop_quality_progress_callbacks,
    _text_scope_blocking_errors,
    issue,
    load_setting,
    native_thread_count,
    rule_contract_issues_to_agent_issues,
)
from app.regex_contract import RegexContractValidationError


class TextIndexAgentMixin:
    """承载 AgentToolkitService 的文本范围索引命令族。"""

    async def rebuild_text_index(
        self: AgentServiceContext,
        *,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """重建当前游戏的持久文本范围索引。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        started_at = time.perf_counter()
        stage_started_at = started_at
        stage_timings: dict[str, int] = {}

        def finish_stage(stage_name: str) -> None:
            nonlocal stage_started_at
            now = time.perf_counter()
            stage_timings[stage_name] = int((now - stage_started_at) * 1000)
            stage_started_at = now

        def base_summary() -> JsonObject:
            return {
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "stage_timings": dict(stage_timings),
                "native_thread_count": native_thread_count(),
            }

        set_progress(0, 5)
        set_status("加载配置和规则")
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(
                self.setting_path,
                overrides=setting_overrides,
                source_language=session.source_language,
            )
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
            advance_progress(1)
            finish_stage("load_config_and_rules")

            set_status("加载翻译源视图")
            game_data = await self._load_translation_source_game_data(
                session,
                include_plugin_source_files=True,
            )
            translated_items = await session.read_translated_items()
            advance_progress(1)
            finish_stage("load_translation_source")

            set_status("构建统一文本范围")
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
                set_progress(5, 5)
                set_status("文本规则检查没通过，未重建文本范围索引")
                summary = base_summary()
                summary.update(
                    {
                        "index_status": "not_rebuilt",
                        "indexed_count": 0,
                        "index_item_count": 0,
                        "include_write_probe": True,
                    }
                )
                return AgentReport.from_parts(
                    errors=rule_contract_issues_to_agent_issues(error),
                    warnings=[],
                    summary=summary,
                    details={},
                )
            finish_stage("build_text_scope")
            blocking_errors = _text_scope_blocking_errors(scope)
            if blocking_errors:
                set_progress(5, 5)
                set_status("检查没通过，未重建文本范围索引")
                summary = base_summary()
                summary.update(
                    {
                        "index_status": "not_rebuilt",
                        "indexed_count": 0,
                        "include_write_probe": True,
                    }
                )
                return AgentReport.from_parts(
                    errors=blocking_errors,
                    warnings=[],
                    summary=summary,
                    details={},
                )
            workflow_gate_errors = await collect_plugin_source_workflow_gate_errors(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )
            if workflow_gate_errors:
                set_progress(5, 5)
                set_status("工作流前置检查没通过，未重建文本范围索引")
                summary = base_summary()
                summary.update(
                    {
                        "index_status": "not_rebuilt",
                        "indexed_count": 0,
                        "include_write_probe": True,
                    }
                )
                return AgentReport.from_parts(
                    errors=[issue(error.code, error.message) for error in workflow_gate_errors],
                    warnings=[],
                    summary=summary,
                    details={},
                )
            advance_progress(1)

            set_status("写入持久文本范围索引")
            metadata = await rebuild_persistent_text_index(
                session=session,
                game_data=game_data,
                setting=setting,
                text_rules=text_rules,
                setting_overrides=setting_overrides,
                scope=scope,
            )
            advance_progress(1)
            finish_stage("write_text_index")

        set_progress(5, 5)
        set_status("文本范围索引重建完成")
        summary = base_summary()
        summary.update(
            {
                "index_status": "rebuilt",
                "indexed_count": metadata.item_count,
                "index_item_count": metadata.item_count,
                "source_snapshot_fingerprint": metadata.source_snapshot_fingerprint,
                "rules_fingerprint": metadata.rules_fingerprint,
                "created_at": metadata.created_at,
                "include_write_probe": True,
                "performance_notes": [
                    "首次重建会完整扫描翻译源视图；后续小任务应复用 warm index。",
                ],
            }
        )
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary=summary,
            details={},
        )
