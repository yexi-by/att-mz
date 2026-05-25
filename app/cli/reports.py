"""命令行报告输出工具。

本模块负责把业务摘要转换为稳定 JSON 报告，并按终端模式渲染用户可扫读表格。
"""

from __future__ import annotations

import argparse

from rich.table import Table

from app.agent_toolkit import AgentIssue, AgentReport
from app.agent_toolkit.reports import issue
from app.application.handler import (
    FontRestoreSummary,
    TerminologyWriteSummary,
    TextTranslationSummary,
    WriteBackSummary,
)
from app.cli.arguments import read_bool_arg, read_optional_path_arg
from app.observability import console, logger
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue


REPORT_STDOUT_SAMPLE_LIMIT = 20


def build_translate_summary_report(summary: TextTranslationSummary) -> AgentReport:
    """把正文翻译摘要转换为稳定 JSON 报告。"""
    warnings: list[AgentIssue] = []
    if summary.has_errors:
        warnings.append(
            issue(
                "translation_quality_errors",
                f"本轮翻译有 {summary.error_count} 条模型翻了但项目检查没通过的译文；可以继续运行 translate，或导出手动填写译文表修复",
            )
        )
    return AgentReport.from_parts(
        errors=[],
        warnings=warnings,
        summary={
            "run_id": summary.run_id,
            "total_extracted_items": summary.total_extracted_items,
            "pending_count": summary.pending_count,
            "deduplicated_count": summary.deduplicated_count,
            "batch_count": summary.batch_count,
            "success_count": summary.success_count,
            "quality_error_count": summary.error_count,
            "llm_failure_count": summary.llm_failure_count,
        },
        details={},
    )


def build_write_back_summary_report(summary: WriteBackSummary) -> AgentReport:
    """把游戏文件回写摘要转换为稳定 JSON 报告。"""
    return AgentReport.from_parts(
        errors=[],
        warnings=[],
        summary=_build_write_back_summary_object(summary),
        details={},
    )


def build_terminology_write_summary_report(summary: TerminologyWriteSummary) -> AgentReport:
    """把术语专用写入摘要转换为稳定 JSON 报告。"""
    return AgentReport.from_parts(
        errors=[],
        warnings=[],
        summary={
            "written_count": summary.written_count,
            "preserved_translation_count": summary.preserved_translation_count,
        },
        details={},
    )


def build_run_all_summary_report(
    *,
    text_summary: TextTranslationSummary,
    write_back_summary: WriteBackSummary | None,
) -> AgentReport:
    """把 `run-all` 翻译和写文件结果转换为稳定 JSON 报告。"""
    write_back_performed = write_back_summary is not None
    summary: JsonObject = {
        "run_id": text_summary.run_id,
        "total_extracted_items": text_summary.total_extracted_items,
        "pending_count": text_summary.pending_count,
        "deduplicated_count": text_summary.deduplicated_count,
        "batch_count": text_summary.batch_count,
        "success_count": text_summary.success_count,
        "quality_error_count": text_summary.error_count,
        "llm_failure_count": text_summary.llm_failure_count,
        "write_back_performed": write_back_performed,
        "write_back_skipped": not write_back_performed,
        "write_back_planned_file_count": 0,
        "write_back_skipped_file_count": 0,
        "write_back_data_item_count": 0,
        "write_back_plugin_item_count": 0,
        "write_back_terminology_written_count": 0,
    }
    details: JsonObject = {
        "translation": _build_translation_summary_object(text_summary),
        "write_back": None,
    }
    if write_back_summary is not None:
        write_summary = _build_write_back_summary_object(write_back_summary)
        summary.update(
            {
                "write_back_planned_file_count": write_back_summary.planned_file_count,
                "write_back_skipped_file_count": write_back_summary.skipped_file_count,
                "write_back_data_item_count": write_back_summary.data_item_count,
                "write_back_plugin_item_count": write_back_summary.plugin_item_count,
                "write_back_terminology_written_count": write_back_summary.terminology_written_count,
            }
        )
        details["write_back"] = write_summary
    return AgentReport.from_parts(errors=[], warnings=[], summary=summary, details=details)


def build_font_restore_summary_report(summary: FontRestoreSummary) -> AgentReport:
    """把字体还原摘要转换为稳定 JSON 报告。"""
    warnings: list[AgentIssue] = []
    if summary.target_font_name is None:
        warnings.append(issue("font_restore", "没有候选覆盖字体名称，无法判断需要还原哪个新字体引用"))
    elif summary.restored_reference_count == 0:
        warnings.append(issue("font_restore", "没有找到需要还原的覆盖字体引用"))
    return AgentReport.from_parts(
        errors=[],
        warnings=warnings,
        summary={
            "restored_field_count": summary.restored_field_count,
            "restored_reference_count": summary.restored_reference_count,
            "target_font_name": summary.target_font_name or "",
        },
        details={},
    )


def build_sampled_stdout_report(
    report: AgentReport,
    *,
    sample_limit: int = REPORT_STDOUT_SAMPLE_LIMIT,
) -> AgentReport:
    """把大报告明细裁剪为适合 stdout 的摘要报告。"""
    return AgentReport(
        status=report.status,
        errors=list(report.errors),
        warnings=list(report.warnings),
        summary=dict(report.summary),
        details=_summarize_json_object(report.details, sample_limit=sample_limit),
    )


def _summarize_json_object(value: JsonObject, *, sample_limit: int) -> JsonObject:
    """递归裁剪 JSON 对象里的数组明细。"""
    summary: JsonObject = {}
    for key, child in value.items():
        summary[key] = _summarize_json_value(child, sample_limit=sample_limit)
    return summary


def _summarize_json_value(value: JsonValue, *, sample_limit: int) -> JsonValue:
    """把 JSON 值转换为摘要值。"""
    if isinstance(value, list):
        return _summarize_json_array(value, sample_limit=sample_limit)
    if isinstance(value, dict):
        return _summarize_json_object(value, sample_limit=sample_limit)
    return value


def _summarize_json_array(value: JsonArray, *, sample_limit: int) -> JsonObject:
    """把数组转换为计数、样例和省略数量。"""
    effective_limit = max(0, sample_limit)
    samples: JsonArray = [
        _summarize_json_value(item, sample_limit=sample_limit)
        for item in value[:effective_limit]
    ]
    return {
        "count": len(value),
        "samples": samples,
        "omitted_count": max(0, len(value) - effective_limit),
    }


def write_report_outputs(
    *,
    report: AgentReport,
    args: argparse.Namespace,
    title: str,
    write_output_file: bool = True,
    stdout_report: AgentReport | None = None,
) -> None:
    """按用户参数输出 Agent 工具包报告。"""
    output_path = read_optional_path_arg(args, "output") if write_output_file else None
    json_text = report.to_json_text()
    display_report = stdout_report or report
    display_json_text = display_report.to_json_text()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _ = output_path.write_text(f"{json_text}\n", encoding="utf-8")

    if read_bool_arg(args, "json_output"):
        print(display_json_text)
        return

    render_agent_report(report=display_report, title=title)
    if output_path is not None:
        logger.success(f"[tag.success]JSON 报告已写出[/tag.success] 文件 [tag.path]{output_path}[/tag.path]")


def render_agent_report(*, report: AgentReport, title: str) -> None:
    """用 Rich 表格展示报告摘要和问题列表。"""
    summary_table = Table(title=title)
    summary_table.add_column("字段", style="cyan")
    summary_table.add_column("值", style="magenta")
    summary_table.add_row("状态", report.status)
    for key, value in report.summary.items():
        summary_table.add_row(key, str(value))
    console.print(summary_table)

    if report.errors:
        error_table = Table(title="必须先处理的错误")
        error_table.add_column("代码", style="red")
        error_table.add_column("说明", style="white")
        for item in report.errors:
            error_table.add_row(item.code, item.message)
        console.print(error_table)

    if report.warnings:
        warning_table = Table(title="告警")
        warning_table.add_column("代码", style="yellow")
        warning_table.add_column("说明", style="white")
        for item in report.warnings:
            warning_table.add_row(item.code, item.message)
        console.print(warning_table)


def _build_translation_summary_object(summary: TextTranslationSummary) -> JsonObject:
    """构建正文翻译摘要 JSON 对象。"""
    return {
        "run_id": summary.run_id,
        "total_extracted_items": summary.total_extracted_items,
        "pending_count": summary.pending_count,
        "deduplicated_count": summary.deduplicated_count,
        "batch_count": summary.batch_count,
        "success_count": summary.success_count,
        "quality_error_count": summary.error_count,
        "llm_failure_count": summary.llm_failure_count,
    }


def _build_write_back_summary_object(summary: WriteBackSummary) -> JsonObject:
    """构建游戏文件写入摘要 JSON 对象。"""
    return {
        "data_item_count": summary.data_item_count,
        "plugin_item_count": summary.plugin_item_count,
        "terminology_written_count": summary.terminology_written_count,
        "target_font_name": summary.target_font_name or "",
        "source_font_count": summary.source_font_count,
        "replaced_font_reference_count": summary.replaced_font_reference_count,
        "font_copied": summary.font_copied,
        "planned_file_count": summary.planned_file_count,
        "skipped_file_count": summary.skipped_file_count,
        "plugin_source_ast_source_scan_file_count": summary.plugin_source_ast_source_scan_file_count,
        "plugin_source_ast_runtime_scan_file_count": summary.plugin_source_ast_runtime_scan_file_count,
        "plugin_source_runtime_map_count": summary.plugin_source_runtime_map_count,
        "pre_write_check_ms": summary.pre_write_check_ms,
        "rust_plan_ms": summary.rust_plan_ms,
        "file_replacement_ms": summary.file_replacement_ms,
        "post_write_audit_ms": summary.post_write_audit_ms,
    }

__all__ = [
    "build_font_restore_summary_report",
    "build_run_all_summary_report",
    "build_sampled_stdout_report",
    "build_terminology_write_summary_report",
    "build_translate_summary_report",
    "build_write_back_summary_report",
    "REPORT_STDOUT_SAMPLE_LIMIT",
    "render_agent_report",
    "write_report_outputs",
]
