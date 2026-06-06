"""Agent 工具箱文本范围索引子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import time

from app.application.flow_gate import (
    collect_indexed_workflow_gate_errors,
    format_workflow_gate_error,
)
from app.native_scope_index import NativeScopeIndexStorageError
from app.rmmz.text_rules import JsonArray, JsonObject
from app.text_index import (
    collect_text_index_external_rule_gate_errors,
    collect_text_index_placeholder_gate_errors,
    collect_text_index_scope_gate_errors,
    rebuild_text_index_native_storage_with_summary,
)

from .common import (
    AgentReport,
    AgentServiceContext,
    QualityProgressCallbacks,
    SettingOverrides,
    TextRules,
    _noop_quality_progress_callbacks,
    issue,
    load_setting,
    native_thread_count,
)


class TextIndexAgentMixin:
    """承载 AgentToolkitService 的文本范围索引命令族。"""

    async def rebuild_text_index(
        self: AgentServiceContext,
        *,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
        include_write_probe: bool = True,
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

        set_progress(0, 3)
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

            set_status("原生重建持久文本范围索引")
            rust_stage_timings: JsonObject = {}
            try:
                native_rebuild = await rebuild_text_index_native_storage_with_summary(
                    session=session,
                    setting=setting,
                    text_rules=text_rules,
                    setting_overrides=setting_overrides,
                    include_write_probe=include_write_probe,
                )
                metadata = native_rebuild.metadata
                raw_rust_stage_timings = native_rebuild.native_summary.get("internal_stage_timings", {})
                if isinstance(raw_rust_stage_timings, dict):
                    rust_stage_timings = {
                        str(key): value
                        for key, value in raw_rust_stage_timings.items()
                        if isinstance(value, int) and value >= 0
                    }
            except NativeScopeIndexStorageError as error:
                error_message = str(error)
                error_code = error.code
                finish_stage("rust_rebuild_text_index")
                set_progress(3, 3)
                set_status("文本范围索引重建失败")
                summary = base_summary()
                summary.update(
                    {
                        "index_status": "rebuild_failed",
                        "indexed_count": 0,
                        "index_item_count": 0,
                        "include_write_probe": include_write_probe,
                    }
                )
                return AgentReport.from_parts(
                    errors=[issue(error_code, error_message)],
                    warnings=[],
                    summary=summary,
                    details={},
                )
            except RuntimeError as error:
                error_message = str(error)
                error_code = (
                    "mv_virtual_namebox_rules_invalid"
                    if "MV 虚拟名字框规则" in error_message
                    else "text_index_rebuild_failed"
                )
                finish_stage("rust_rebuild_text_index")
                set_progress(3, 3)
                set_status("文本范围索引重建失败")
                summary = base_summary()
                summary.update(
                    {
                        "index_status": "rebuild_failed",
                        "indexed_count": 0,
                        "index_item_count": 0,
                        "include_write_probe": include_write_probe,
                    }
                )
                return AgentReport.from_parts(
                    errors=[issue(error_code, error_message)],
                    warnings=[],
                    summary=summary,
                    details={},
                )
            advance_progress(1)
            finish_stage("rust_rebuild_text_index")

            set_status("检查源分支前置条件")
            source_branch_gate_summary: str | None = None
            source_branch_gate_details: JsonArray = []
            external_rule_gate_errors = await collect_text_index_external_rule_gate_errors(
                session=session,
                metadata=metadata,
            )
            placeholder_gate_errors = await collect_text_index_placeholder_gate_errors(
                session=session,
                metadata=metadata,
                custom_placeholder_rules_supplied=False,
            )
            text_scope_gate_errors = await collect_text_index_scope_gate_errors(session=session)
            workflow_gate_errors = await collect_indexed_workflow_gate_errors(
                session=session,
                text_rules=text_rules,
                custom_placeholder_rules_supplied=False,
                scope=None,
                plugin_source_rule_gate_errors=[],
                nonstandard_data_rule_gate_errors=[],
                external_rule_gate_errors=external_rule_gate_errors,
                placeholder_gate_errors=placeholder_gate_errors,
                text_scope_gate_errors=text_scope_gate_errors,
            )
            source_branch_gate_status = "prechecked"
            if workflow_gate_errors:
                source_branch_gate_status = "needs_review"
                source_branch_gate_summary = format_workflow_gate_error(workflow_gate_errors)
                source_branch_gate_details = [
                    {"code": item.code, "message": item.message}
                    for item in workflow_gate_errors
                ]

        set_progress(3, 3)
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
                "include_write_probe": include_write_probe,
                "source_branch_gate_status": source_branch_gate_status,
                "rust_stage_timings": rust_stage_timings,
                "performance_notes": [
                    "首次重建由 Rust 直读游戏目录并写入持久索引；后续小任务应复用 warm index。",
                ],
            }
        )
        if source_branch_gate_summary is not None:
            summary["source_branch_gate_summary"] = source_branch_gate_summary
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary=summary,
            details={"source_branch_gate_errors": source_branch_gate_details},
        )
