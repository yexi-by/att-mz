"""统一文本范围服务中的写入可行性探针。"""

from __future__ import annotations

from app.native_quality import collect_native_write_protocol_details
from app.plugin_source_text.extraction import parse_plugin_source_location_path
from app.plugin_source_text.models import PluginSourceScan
from app.rmmz.schema import GameData, TranslationItem
from app.rmmz.text_rules import JsonArray

from .models import WriteBackProbeError


def collect_write_back_probe_reasons(
    *,
    game_data: GameData,
    active_items: list[TranslationItem],
    plugin_source_scan: PluginSourceScan | None = None,
) -> dict[str, str]:
    """用真实写入协议探针标记当前文本清单中的不可写条目。"""
    if not active_items:
        return {}
    probe_items = [_build_write_back_probe_item(item) for item in active_items]
    try:
        details = collect_native_write_protocol_details(
            game_data=game_data.data,
            plugins_js=[plugin for plugin in game_data.plugins_js],
            items=probe_items,
        )
    except Exception as error:
        raise WriteBackProbeError(f"写入协议探针失败: {type(error).__name__}: {error}") from error
    reasons = _write_protocol_reasons_by_path(details)
    reasons.update(
        _collect_plugin_source_write_back_probe_reasons(
            game_data=game_data,
            probe_items=probe_items,
            plugin_source_scan=plugin_source_scan,
        )
    )
    return reasons


def _collect_plugin_source_write_back_probe_reasons(
    *,
    game_data: GameData,
    probe_items: list[TranslationItem],
    plugin_source_scan: PluginSourceScan | None,
) -> dict[str, str]:
    """用 Rust AST 检查插件源码 selector 是否仍可确定写入。"""
    items_by_file: dict[str, list[tuple[str, TranslationItem]]] = {}
    reasons: dict[str, str] = {}
    for item in probe_items:
        parsed = parse_plugin_source_location_path(item.location_path)
        if parsed is None:
            continue
        file_name, selector = parsed
        items_by_file.setdefault(file_name, []).append((selector, item))
    if not items_by_file:
        return {}
    source_files: dict[str, str] = {}
    for file_name, file_items in sorted(items_by_file.items()):
        source = game_data.plugin_source_files.get(file_name)
        if source is None:
            for _selector, item in file_items:
                reasons[item.location_path] = f"插件源码文件不存在: {file_name}"
            continue
        source_files[file_name] = source
    if not source_files:
        return reasons
    if plugin_source_scan is not None:
        return _collect_plugin_source_write_back_probe_reasons_from_scan(
            file_items_by_name=items_by_file,
            source_file_names=frozenset(source_files),
            plugin_source_scan=plugin_source_scan,
            reasons=reasons,
        )
    affected = ", ".join(sorted(source_files))
    raise WriteBackProbeError(
        "插件源码写入探针缺少当前文本索引中的源码扫描结果，"
        + f"当前插件源码扫描结果缺失，不能继续执行: {affected}。"
        + "下一步：请运行 rebuild-text-index；如果插件源码规则来自导出文件，请重新导出并导入插件源码规则。"
    )


def _collect_plugin_source_write_back_probe_reasons_from_scan(
    *,
    file_items_by_name: dict[str, list[tuple[str, TranslationItem]]],
    source_file_names: frozenset[str],
    plugin_source_scan: PluginSourceScan,
    reasons: dict[str, str],
) -> dict[str, str]:
    """复用已构建的插件源码扫描事实校验写回 selector。"""
    file_scans = {file_scan.file_name: file_scan for file_scan in plugin_source_scan.files}
    for file_name, file_items in sorted(file_items_by_name.items()):
        if file_name not in source_file_names:
            continue
        syntax_error = plugin_source_scan.syntax_errors.get(file_name)
        if syntax_error is not None:
            for _selector, item in file_items:
                reasons[item.location_path] = f"插件源码 AST 检查失败: {syntax_error}"
            continue
        file_scan = file_scans.get(file_name)
        if file_scan is None:
            for _selector, item in file_items:
                reasons[item.location_path] = f"插件源码 AST 检查失败: 批量 AST 结果缺少文件: {file_name}"
            continue
        candidates_by_selector = {candidate.selector: candidate for candidate in file_scan.candidates}
        for selector, item in file_items:
            candidate = candidates_by_selector.get(selector)
            if candidate is None:
                reasons[item.location_path] = f"插件源码 selector 已失效: {item.location_path}"
                continue
            if item.original_lines != [candidate.text]:
                reasons[item.location_path] = f"插件源码原文已变化，请重新导出 AST 地图: {item.location_path}"
                continue
            if len(item.translation_lines) != 1:
                reasons[item.location_path] = f"插件源码短文本只能写入 1 行译文: {item.location_path}"
    return reasons


def _build_write_back_probe_item(item: TranslationItem) -> TranslationItem:
    """生成不依赖模型译文的结构性写入探针条目。"""
    if item.item_type == "array":
        translation_lines = ["回写校验" for _line in item.original_lines]
    else:
        translation_lines = ["回写校验"]
    return item.model_copy(update={"translation_lines": translation_lines}, deep=False)


def _write_protocol_reasons_by_path(details: JsonArray) -> dict[str, str]:
    """把写入协议明细压成定位路径到原因的索引。"""
    reasons: dict[str, str] = {}
    for detail in details:
        if not isinstance(detail, dict):
            continue
        location_path = detail.get("location_path")
        if not isinstance(location_path, str):
            continue
        reason_value = detail.get("reason")
        if not isinstance(reason_value, str) or not reason_value.strip():
            reason_value = detail.get("message")
        if not isinstance(reason_value, str) or not reason_value.strip():
            reason_value = "写入协议预演失败"
        reasons[location_path] = reason_value
    return reasons
