use super::models::{TextPlanRules, TranslationItem};
use super::text_prepare::prepared_long_lines;
use crate::native_core::models::{
    NativeSourceResidualRule, NativeTextRules, NativeTranslationItem,
};
use crate::native_core::quality::scan_quality_items;
use serde_json::Value;

pub(super) fn assert_saved_translation_quality_passed(
    items: &[TranslationItem],
    text_rules: NativeTextRules,
    source_residual_rules: Vec<NativeSourceResidualRule>,
) -> Result<(), String> {
    let quality = scan_quality_items(
        items
            .iter()
            .map(native_quality_item_from_translation)
            .collect(),
        text_rules,
        source_residual_rules,
    )?;
    let mut messages = Vec::new();
    if !quality.placeholder_risk_items.is_empty() {
        let mut message = format!(
            "发现 {} 条译文里的游戏控制符可能被改坏",
            quality.placeholder_risk_items.len()
        );
        append_first_quality_detail(&mut message, &quality.placeholder_risk_items);
        messages.push(message);
    }
    if !quality.source_residual_items.is_empty() {
        let mut message = format!(
            "发现 {} 条译文存在源文残留风险",
            quality.source_residual_items.len()
        );
        append_first_quality_detail(&mut message, &quality.source_residual_items);
        messages.push(message);
    }
    if !quality.text_structure_items.is_empty() {
        let mut message = format!(
            "发现 {} 条译文改动了游戏文本结构",
            quality.text_structure_items.len()
        );
        append_first_quality_detail(&mut message, &quality.text_structure_items);
        messages.push(message);
    }
    if !quality.overwide_line_items.is_empty() {
        let mut message = format!(
            "发现 {} 行译文超过当前长文本宽度上限",
            quality.overwide_line_items.len()
        );
        append_first_quality_detail(&mut message, &quality.overwide_line_items);
        messages.push(message);
    }
    if messages.is_empty() {
        return Ok(());
    }
    Err(format!("写进游戏文件前检查没通过：{}", messages.join("；")))
}

pub(super) fn append_first_quality_detail(message: &mut String, items: &[Value]) {
    if let Some(reason) = first_quality_reason(items) {
        message.push_str(&format!("：{reason}"));
    }
    if let Some(location_path) = first_quality_location(items) {
        message.push_str(&format!("；文本在游戏里的内部位置: {location_path}"));
    }
}

pub(super) fn quality_gate_items_for_write_plan(
    items: &[TranslationItem],
    rules: &TextPlanRules,
) -> Result<Vec<TranslationItem>, String> {
    let mut quality_items = Vec::with_capacity(items.len());
    for item in items {
        let mut quality_item = item.clone();
        if item.item_type == "long_text" {
            quality_item.translation_lines = prepared_long_lines(item, rules)?;
        }
        quality_items.push(quality_item);
    }
    Ok(quality_items)
}

pub(super) fn first_quality_reason(items: &[Value]) -> Option<&str> {
    items
        .first()
        .and_then(|item| item.get("reason"))
        .and_then(Value::as_str)
}

pub(super) fn first_quality_location(items: &[Value]) -> Option<&str> {
    items
        .first()
        .and_then(|item| item.get("location_path"))
        .and_then(Value::as_str)
}

pub(super) fn native_quality_item_from_translation(
    item: &TranslationItem,
) -> NativeTranslationItem {
    NativeTranslationItem {
        location_path: item.location_path.clone(),
        item_type: item.item_type.clone(),
        role: item.role.clone(),
        original_lines: item.original_lines.clone(),
        translation_lines: item.translation_lines.clone(),
    }
}
