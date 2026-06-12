//! 翻译质量检查编排。
//!
//! 本模块负责解析质量检查输入、并行调度各类检查，并保持 PyO3 门面的输出协议稳定。

mod line_width;
mod placeholder;
mod residual;
mod structure;

use rayon::prelude::*;
use std::sync::Arc;

use super::details::collect_sorted_details;
use super::models::{QualityPayload, QualityScanCountOutput, QualityScanOutput};
use super::pool::run_with_optional_pool;
use super::rules::compile_rules;
use line_width::collect_overwide_details;
use placeholder::collect_placeholder_detail;
use residual::{collect_residual_detail, index_residual_rules};
use structure::collect_text_structure_detail;

/// 扫描翻译质量问题并返回稳定 JSON 字符串。
pub fn scan_quality_impl(payload_json: &str) -> Result<String, String> {
    let payload: QualityPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("Rust 质检输入 JSON 解析失败: {error}"))?;
    let output = scan_quality_items(
        payload.items,
        payload.text_rules,
        payload.source_residual_rules,
    )?;

    serde_json::to_string(&output)
        .map_err(|error| format!("Rust 质检输出 JSON 序列化失败: {error}"))
}

/// 扫描翻译质量问题并只返回计数。
pub fn scan_quality_counts_impl(payload_json: &str) -> Result<String, String> {
    let payload: QualityPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("Rust 质检计数输入 JSON 解析失败: {error}"))?;
    let output = scan_quality_items(
        payload.items,
        payload.text_rules,
        payload.source_residual_rules,
    )?;
    let counts = QualityScanCountOutput {
        source_residual_count: output.source_residual_items.len(),
        text_structure_count: output.text_structure_items.len(),
        placeholder_risk_count: output.placeholder_risk_items.len(),
        overwide_line_count: output.overwide_line_items.len(),
    };
    serde_json::to_string(&counts)
        .map_err(|error| format!("Rust 质检计数输出 JSON 序列化失败: {error}"))
}

/// 扫描翻译质量问题并返回结构化明细。
pub(crate) fn scan_quality_items(
    items: Vec<super::models::NativeTranslationItem>,
    text_rules: super::models::NativeTextRules,
    source_residual_rules: Vec<super::models::NativeSourceResidualRule>,
) -> Result<QualityScanOutput, String> {
    let rules = Arc::new(compile_rules(text_rules)?);
    let residual_rules = Arc::new(index_residual_rules(source_residual_rules)?);
    let items = Arc::new(items);

    run_with_optional_pool(|| {
        let source_residual_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_residual_detail(item, &rules, &residual_rules))
                .collect(),
        );
        let text_structure_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_text_structure_detail(item, &rules))
                .collect(),
        );
        let placeholder_risk_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_placeholder_detail(item, &rules))
                .collect(),
        );
        let overwide_line_items = collect_sorted_details(
            items
                .par_iter()
                .flat_map(|item| collect_overwide_details(item, &rules))
                .collect(),
        );

        QualityScanOutput {
            source_residual_items,
            text_structure_items,
            placeholder_risk_items,
            overwide_line_items,
        }
    })
}

#[cfg(test)]
mod tests {
    use super::scan_quality_impl;
    use serde_json::{Value, json};

    fn quality_payload(items: Value) -> Value {
        json!({
            "items": items,
            "text_rules": {
                "custom_placeholder_rules": [],
                "structured_placeholder_rules": [],
                "source_residual_allowed_chars": ["ぁ-んァ-ヶ一-龯"],
                "source_residual_allowed_tail_chars": [],
                "source_residual_segment_pattern": "[ぁ-んァ-ヶ一-龯]+",
                "source_residual_label": "源文",
                "allowed_source_residual_terms": [],
                "source_residual_terms_ignore_case": false,
                "source_residual_detection_profile": "japanese_strict",
                "english_source_copy_min_words": 4,
                "english_source_copy_min_letters": 12,
                "line_width_count_pattern": "[\\s\\S]",
                "residual_escape_sequence_pattern": "\\\\[A-Za-z]+(?:\\[[^\\]]*\\])?",
                "long_text_line_width_limit": 4
            },
            "source_residual_rules": []
        })
    }

    #[test]
    fn quality_scan_reports_structure_errors_and_overwide_display_lines() {
        let payload = quality_payload(json!([
            {
                "location_path": "Map001.json/1/short/literal",
                "item_type": "short_text",
                "role": null,
                "original_lines": ["説明\\n本文"],
                "translation_lines": ["说明"]
            },
            {
                "location_path": "Map001.json/1/short/width",
                "item_type": "short_text",
                "role": null,
                "original_lines": ["元\n短"],
                "translation_lines": ["甲乙丙丁戊\n短"]
            },
            {
                "location_path": "Map001.json/1/long/artifact",
                "item_type": "long_text",
                "role": null,
                "original_lines": ["原文"],
                "translation_lines": ["正文", ""]
            }
        ]));

        let output_text = scan_quality_impl(&payload.to_string()).expect("质检应成功");
        let output: Value = serde_json::from_str(&output_text).expect("输出应是 JSON");

        let structure_reasons = output["text_structure_items"]
            .as_array()
            .expect("结构错误应为数组")
            .iter()
            .map(|item| item["reason"].as_str().unwrap_or(""))
            .collect::<Vec<_>>();
        assert!(
            structure_reasons
                .iter()
                .any(|reason| reason.contains("字面量换行标记数量不一致"))
        );
        assert!(
            structure_reasons
                .iter()
                .any(|reason| reason.contains("原文没有空行"))
        );
        assert_eq!(output["overwide_line_items"][0]["line_index"], json!(0));
        assert_eq!(
            output["overwide_line_items"][0]["line"],
            json!("甲乙丙丁戊")
        );
    }

    #[test]
    fn quality_scan_reports_control_code_split_hint_on_placeholder_risk() {
        let payload = quality_payload(json!([
            {
                "location_path": "CommonEvents.json/1/0",
                "item_type": "long_text",
                "role": null,
                "original_lines": ["こんにちは"],
                "translation_lines": [r"\fb21st"]
            }
        ]));

        let output_text = scan_quality_impl(&payload.to_string()).expect("质检应成功");
        let output: Value = serde_json::from_str(&output_text).expect("输出应是 JSON");
        let item = &output["placeholder_risk_items"][0];

        assert_eq!(item["location_path"], json!("CommonEvents.json/1/0"));
        assert_eq!(item["hint"]["hint_kind"], json!("possible_control_split"));
        assert_eq!(item["hint"]["original"], json!(r"\fb21st"));
        assert_eq!(item["hint"]["candidate"], json!(r"\fb21"));
        assert_eq!(item["hint"]["possible_split"]["control"], json!(r"\fb2"));
        assert_eq!(item["hint"]["possible_split"]["tail"], json!("1st"));
    }

    #[test]
    fn quality_scan_reports_english_long_residual_without_original() {
        let mut payload = quality_payload(json!([
            {
                "location_path": "Plugin.js/string@1:1",
                "item_type": "short_text",
                "role": null,
                "original_lines": [],
                "translation_lines": ["alpha beta gamma delta"]
            }
        ]));
        payload["text_rules"]["source_residual_segment_pattern"] = json!(r"[A-Za-z]+");
        payload["text_rules"]["source_residual_detection_profile"] = json!("english_source_copy");
        payload["text_rules"]["english_source_copy_min_words"] = json!(4);
        payload["text_rules"]["english_source_copy_min_letters"] = json!(12);

        let output_text = scan_quality_impl(&payload.to_string()).expect("质检应成功");
        let output: Value = serde_json::from_str(&output_text).expect("输出应是 JSON");

        assert_eq!(
            output["source_residual_items"][0]["location_path"],
            json!("Plugin.js/string@1:1")
        );
        assert!(
            output["source_residual_items"][0]["reason"]
                .as_str()
                .expect("reason should be text")
                .contains("alpha beta gamma delta")
        );
    }
}
