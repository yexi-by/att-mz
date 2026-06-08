"""写入游戏文件前的质量硬闸。

本模块只依赖应用层、持久化层和原生质检适配层，供 CLI 和直接业务调用共同阻止
有质量错误的译文写进游戏文件。
"""

from dataclasses import dataclass

from app.application.errors import WriteBackGateError
from app.config.schemas import Setting
from app.native_quality import collect_native_quality_counts, count_native_write_protocol_issues
from app.persistence import TargetGameSession
from app.rmmz.schema import GameData, TranslationItem
from app.rmmz.text_rules import TextRules
from app.text_scope import TextScopeResult


@dataclass(frozen=True, slots=True)
class WriteBackQualityIssue:
    """单个会阻止写入游戏文件的质量错误。"""

    code: str
    message: str


async def assert_write_back_quality_passed(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    translated_items: list[TranslationItem],
    require_complete_translation: bool,
    scope: TextScopeResult | None = None,
    include_native_checks: bool = True,
) -> None:
    """质量检查未通过时直接中断写入游戏文件。"""
    errors = await collect_write_back_quality_errors(
        session=session,
        game_data=game_data,
        setting=setting,
        text_rules=text_rules,
        translated_items=translated_items,
        require_complete_translation=require_complete_translation,
        scope=scope,
        include_native_checks=include_native_checks,
    )
    if errors:
        messages = "；".join(error.message for error in errors)
        raise WriteBackGateError(f"写进游戏文件前检查没通过：{messages}")


async def collect_write_back_quality_errors(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    translated_items: list[TranslationItem],
    require_complete_translation: bool,
    scope: TextScopeResult | None = None,
    include_native_checks: bool = True,
) -> list[WriteBackQualityIssue]:
    """收集当前已保存译文是否允许写入游戏文件的质量错误。"""
    if scope is None:
        raise RuntimeError("collect_write_back_quality_errors 需要调用者传入 Rust/index 生成的文本范围，不能回退构建 Python 完整文本范围")
    errors: list[WriteBackQualityIssue] = []
    active_items = scope.active_items()
    active_items_by_fact_id = _translation_items_by_required_fact_id(
        active_items,
        label="当前文本范围",
    )
    translated_items_by_fact_id = _translation_items_by_required_fact_id(
        translated_items,
        label="已保存译文",
    )
    writable_paths = scope.writable_paths
    active_fact_ids = set(active_items_by_fact_id)
    writable_fact_ids: set[str] = set()
    for item in active_items:
        if item.fact_id is not None and item.location_path in writable_paths:
            writable_fact_ids.add(item.fact_id)
    translated_fact_ids = set(translated_items_by_fact_id)
    pending_fact_ids = writable_fact_ids - translated_fact_ids
    stale_fact_ids = translated_fact_ids - writable_fact_ids
    active_translated_items = [
        item
        for item in translated_items
        if item.fact_id in active_fact_ids
    ]

    if require_complete_translation and pending_fact_ids:
        errors.append(
            WriteBackQualityIssue(
                code="coverage_missing_translation",
                message=f"还有 {len(pending_fact_ids)} 条文本没有成功保存译文",
            )
        )
    if stale_fact_ids:
        errors.append(
            WriteBackQualityIssue(
                code="stale_saved_translations",
                message=f"发现 {len(stale_fact_ids)} 条已保存译文不在当前可写文本范围内",
            )
        )

    latest_run = await session.read_latest_translation_run()
    if require_complete_translation and latest_run is not None:
        active_quality_errors = (
            await session.read_translation_quality_errors_by_fact_ids(
                latest_run.run_id,
                pending_fact_ids,
            )
            if pending_fact_ids
            else []
        )
        llm_failures = await session.read_llm_failures(latest_run.run_id)
        if active_quality_errors:
            errors.append(
                WriteBackQualityIssue(
                    code="translation_quality_errors",
                    message=f"最新翻译运行有 {len(active_quality_errors)} 条模型翻了但项目检查没通过的译文",
                )
            )
        if llm_failures and pending_fact_ids:
            errors.append(
                WriteBackQualityIssue(
                    code="llm_failures",
                    message=f"最新翻译运行存在 {len(llm_failures)} 条模型运行故障",
                )
            )

    if include_native_checks:
        source_residual_rules = await session.read_source_residual_rules()
        native_quality = collect_native_quality_counts(
            items=active_translated_items,
            text_rules=text_rules,
            source_residual_rules=source_residual_rules,
        )
        if native_quality.placeholder_risk_count:
            errors.append(
                WriteBackQualityIssue(
                    code="placeholder_risk",
                    message=f"发现 {native_quality.placeholder_risk_count} 条译文里的游戏控制符可能被改坏",
                )
            )
        if native_quality.source_residual_count:
            errors.append(
                WriteBackQualityIssue(
                    code="source_residual",
                    message=f"发现 {native_quality.source_residual_count} 条译文存在{setting.text_rules.source_residual_label}残留风险",
                )
            )
        if native_quality.text_structure_count:
            errors.append(
                WriteBackQualityIssue(
                    code="text_structure",
                    message=f"发现 {native_quality.text_structure_count} 条译文改动了游戏文本结构",
                )
            )
        if native_quality.overwide_line_count:
            errors.append(
                WriteBackQualityIssue(
                    code="overwide_line",
                    message=f"发现 {native_quality.overwide_line_count} 行译文超过当前长文本宽度上限",
                )
            )

    if include_native_checks and not scope.write_back_probe_error:
        protocol_count = count_native_write_protocol_issues(
            game_data=game_data.data,
            plugins_js=[plugin for plugin in game_data.plugins_js],
            items=active_translated_items,
        )
        if protocol_count:
            errors.append(
                WriteBackQualityIssue(
                    code="write_back_protocol",
                    message=f"发现 {protocol_count} 条译文写回后会破坏游戏或插件解析协议",
                )
            )
    return errors


def _translation_items_by_required_fact_id(
    items: list[TranslationItem],
    *,
    label: str,
) -> dict[str, TranslationItem]:
    """按 fact_id 索引译文条目；缺失或重复说明当前事实身份不可判定。"""
    items_by_fact_id: dict[str, TranslationItem] = {}
    for item in items:
        if not item.fact_id:
            raise ValueError(f"{label}缺少 v2 fact_id，无法判断已翻译事实身份: {item.location_path}")
        if item.fact_id in items_by_fact_id:
            raise ValueError(f"{label}包含重复 v2 fact_id，无法判断已翻译事实身份: {item.fact_id}")
        items_by_fact_id[item.fact_id] = item
    return items_by_fact_id


__all__: list[str] = [
    "WriteBackQualityIssue",
    "assert_write_back_quality_passed",
    "collect_write_back_quality_errors",
]
