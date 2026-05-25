use super::models::{
    PluginSourceReplacement, PluginSourceReplacementResult, RuntimeWriteMap, TranslationItem,
};
use super::utils::{current_timestamp_text, sha256_text, sha256_translation_lines};
use crate::native_core::javascript_ast::{JavaScriptStringSpan, parse_javascript_string_spans};
use rayon::prelude::*;
use sha1::{Digest, Sha1};
use std::collections::{BTreeMap, HashMap};

pub(super) struct PluginSourceWriteResult {
    pub(super) output_files: BTreeMap<String, String>,
    pub(super) runtime_maps: Vec<RuntimeWriteMap>,
    pub(super) source_ast_scan_file_count: usize,
    pub(super) runtime_ast_scan_file_count: usize,
}

pub(super) fn write_plugin_source_files(
    source_files: BTreeMap<String, String>,
    items: Vec<TranslationItem>,
    include_unmodified_files: bool,
) -> Result<PluginSourceWriteResult, String> {
    let mut items_by_file: HashMap<String, Vec<(String, TranslationItem)>> = HashMap::new();
    for item in items {
        let (file_name, selector) = parse_plugin_source_location_path(&item.location_path)?;
        items_by_file
            .entry(file_name)
            .or_default()
            .push((selector, item));
    }
    let created_at = current_timestamp_text()?;
    let results: Vec<(String, String, Vec<RuntimeWriteMap>)> = items_by_file
        .into_par_iter()
        .map(|(file_name, file_items)| {
            let source = source_files
                .get(&file_name)
                .ok_or_else(|| format!("插件源码文件不存在: {file_name}"))?
                .clone();
            let (content, maps) =
                write_single_plugin_source_file(&file_name, &source, file_items, &created_at)?;
            Ok((file_name, content, maps))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let mut runtime_maps: Vec<RuntimeWriteMap> = Vec::new();
    let mut output_files = if include_unmodified_files {
        source_files
    } else {
        BTreeMap::new()
    };
    for (file_name, content, maps) in results {
        output_files.insert(file_name, content);
        runtime_maps.extend(maps);
    }
    let ast_scan_file_count = runtime_maps
        .iter()
        .map(|map| map.source_file_name.as_str())
        .collect::<std::collections::BTreeSet<_>>()
        .len();
    runtime_maps.sort_by(|left, right| left.location_path.cmp(&right.location_path));
    Ok(PluginSourceWriteResult {
        output_files,
        runtime_maps,
        source_ast_scan_file_count: ast_scan_file_count,
        runtime_ast_scan_file_count: ast_scan_file_count,
    })
}

pub(super) fn write_single_plugin_source_file(
    file_name: &str,
    source: &str,
    file_items: Vec<(String, TranslationItem)>,
    created_at: &str,
) -> Result<(String, Vec<RuntimeWriteMap>), String> {
    let scan = parse_javascript_string_spans(source)?;
    if scan.has_error {
        return Err(format!("插件源码 JS 语法检查失败: {file_name}"));
    }
    let source_file_hash = sha256_text(source);
    let mut spans_by_selector: HashMap<String, (JavaScriptStringSpan, String, String)> =
        HashMap::new();
    for span in scan.spans {
        let raw_text = source
            .get(span.content_start_byte_index..span.content_end_byte_index)
            .ok_or_else(|| format!("插件源码字符串范围无效: {file_name}"))?
            .to_string();
        let selector = candidate_selector_for_span(span.start_index, span.end_index, &raw_text);
        let visible_text = normalize_visible_text_for_extraction(&unescape_js_text(&raw_text));
        spans_by_selector.insert(selector, (span, raw_text, visible_text));
    }
    let mut replacements: Vec<PluginSourceReplacement> = Vec::new();
    for (selector, item) in file_items {
        let (span, _raw_text, visible_text) = spans_by_selector
            .get(&selector)
            .ok_or_else(|| format!("插件源码 selector 已失效: {}", item.location_path))?
            .clone();
        if item.original_lines != vec![visible_text.clone()] {
            return Err(format!(
                "插件源码原文已变化，请重新导出 AST 地图: {}",
                item.location_path
            ));
        }
        if item.translation_lines.len() != 1 {
            return Err(format!(
                "插件源码短文本只能写入 1 行译文: {}",
                item.location_path
            ));
        }
        let translated_text = item
            .translation_lines
            .first()
            .ok_or_else(|| format!("插件源码译文行为空: {}", item.location_path))?
            .trim()
            .to_string();
        let written_text = escape_js_string_content(&translated_text, &span.quote);
        replacements.push(PluginSourceReplacement {
            selector,
            item,
            span,
            visible_text,
            written_text,
            source_file_hash: source_file_hash.clone(),
        });
    }
    replacements.sort_by_key(|replacement| replacement.span.content_start_index);
    let (content, replacement_results) = apply_plugin_source_replacements(source, replacements)?;
    let runtime_scan = parse_javascript_string_spans(&content)
        .map_err(|error| format!("插件源码替换后 JS 语法检查失败 {file_name}: {error}"))?;
    if runtime_scan.has_error {
        return Err(format!("插件源码替换后 JS 语法检查失败: {file_name}"));
    }
    let runtime_file_hash = sha256_text(&content);
    let runtime_spans_by_selector =
        runtime_spans_by_selector(file_name, &content, runtime_scan.spans)?;
    let mut maps: Vec<RuntimeWriteMap> = Vec::new();
    for result in replacement_results {
        assert_runtime_replacement_mapped(file_name, &result, &runtime_spans_by_selector)?;
        maps.push(RuntimeWriteMap {
            location_path: result.replacement.item.location_path.clone(),
            source_file_name: file_name.to_string(),
            source_selector: result.replacement.selector.clone(),
            source_file_hash: result.replacement.source_file_hash.clone(),
            source_text_hash: sha256_text(&result.replacement.visible_text),
            translation_lines_hash: sha256_translation_lines(
                &result.replacement.item.translation_lines,
            )?,
            runtime_file_name: file_name.to_string(),
            runtime_selector: result.runtime_selector,
            runtime_file_hash: runtime_file_hash.clone(),
            runtime_text_hash: sha256_text(&normalize_visible_text_for_extraction(
                &unescape_js_text(&result.replacement.written_text),
            )),
            runtime_line: result.runtime_line,
            created_at: created_at.to_string(),
        });
    }
    Ok((content, maps))
}

fn runtime_spans_by_selector(
    file_name: &str,
    content: &str,
    spans: Vec<JavaScriptStringSpan>,
) -> Result<HashMap<String, String>, String> {
    let mut spans_by_selector: HashMap<String, String> = HashMap::new();
    for span in spans {
        let raw_text = content
            .get(span.content_start_byte_index..span.content_end_byte_index)
            .ok_or_else(|| format!("插件源码替换后字符串范围无效: {file_name}"))?
            .to_string();
        let selector = candidate_selector_for_span(span.start_index, span.end_index, &raw_text);
        spans_by_selector.insert(selector, raw_text);
    }
    Ok(spans_by_selector)
}

fn assert_runtime_replacement_mapped(
    file_name: &str,
    result: &PluginSourceReplacementResult,
    runtime_spans_by_selector: &HashMap<String, String>,
) -> Result<(), String> {
    let Some(runtime_raw_text) = runtime_spans_by_selector.get(&result.runtime_selector) else {
        return Err(format!(
            "插件源码替换后 runtime selector 未出现在最终 AST: {file_name}: {} -> {}",
            result.replacement.item.location_path, result.runtime_selector
        ));
    };
    if runtime_raw_text != &result.replacement.written_text {
        return Err(format!(
            "插件源码替换后 runtime selector 指向的文本与写入文本不一致: {file_name}: {}",
            result.replacement.item.location_path
        ));
    }
    let runtime_visible_text =
        normalize_visible_text_for_extraction(&unescape_js_text(runtime_raw_text));
    let expected_visible_text =
        normalize_visible_text_for_extraction(&unescape_js_text(&result.replacement.written_text));
    if runtime_visible_text != expected_visible_text {
        return Err(format!(
            "插件源码替换后 runtime selector 可见文本不一致: {file_name}: {}",
            result.replacement.item.location_path
        ));
    }
    Ok(())
}

pub(super) fn apply_plugin_source_replacements(
    source: &str,
    replacements: Vec<PluginSourceReplacement>,
) -> Result<(String, Vec<PluginSourceReplacementResult>), String> {
    let mut parts: Vec<String> = Vec::new();
    let mut current_source_byte_index = 0usize;
    let mut current_runtime_index = 0usize;
    let mut current_runtime_line = 1i64;
    let mut results: Vec<PluginSourceReplacementResult> = Vec::new();
    for replacement in replacements {
        let unchanged = source
            .get(current_source_byte_index..replacement.span.content_start_byte_index)
            .ok_or_else(|| "插件源码替换范围无效".to_string())?;
        parts.push(unchanged.to_string());
        current_runtime_index += unchanged.chars().count();
        current_runtime_line += unchanged
            .chars()
            .filter(|char_value| *char_value == '\n')
            .count() as i64;
        let runtime_content_start_index = current_runtime_index;
        let runtime_line = current_runtime_line;
        parts.push(replacement.written_text.clone());
        current_runtime_index += replacement.written_text.chars().count();
        current_runtime_line += replacement
            .written_text
            .chars()
            .filter(|char_value| *char_value == '\n')
            .count() as i64;
        let runtime_content_end_index = current_runtime_index;
        current_source_byte_index = replacement.span.content_end_byte_index;
        let literal_prefix_length =
            replacement.span.content_start_index - replacement.span.start_index;
        let literal_suffix_length = replacement.span.end_index - replacement.span.content_end_index;
        let runtime_start_index = runtime_content_start_index.saturating_sub(literal_prefix_length);
        let runtime_end_index = runtime_content_end_index + literal_suffix_length;
        let runtime_selector = candidate_selector_for_span(
            runtime_start_index,
            runtime_end_index,
            &replacement.written_text,
        );
        results.push(PluginSourceReplacementResult {
            replacement,
            runtime_selector,
            runtime_line,
        });
    }
    let tail = source
        .get(current_source_byte_index..)
        .ok_or_else(|| "插件源码尾部范围无效".to_string())?;
    parts.push(tail.to_string());
    Ok((parts.join(""), results))
}

pub(super) fn parse_plugin_source_location_path(
    location_path: &str,
) -> Result<(String, String), String> {
    let rest = location_path
        .strip_prefix("js/plugins/")
        .ok_or_else(|| format!("插件源码路径前缀无效: {location_path}"))?;
    let slash_index = rest
        .find('/')
        .ok_or_else(|| format!("插件源码路径缺少 selector: {location_path}"))?;
    let file_name = rest[..slash_index].trim();
    let selector = rest[slash_index + 1..].trim();
    if file_name.is_empty() || selector.is_empty() {
        return Err(format!("插件源码路径不完整: {location_path}"));
    }
    Ok((file_name.to_string(), selector.to_string()))
}

pub(super) fn candidate_selector_for_span(
    start_index: usize,
    end_index: usize,
    raw_text: &str,
) -> String {
    let mut hasher = Sha1::new();
    hasher.update(raw_text.as_bytes());
    let digest = hasher.finalize();
    let mut hex_text = String::new();
    for byte in digest.iter().take(6) {
        hex_text.push_str(&format!("{byte:02x}"));
    }
    format!("ast:string:{start_index}:{end_index}:{hex_text}")
}

pub(super) fn escape_js_string_content(text: &str, quote: &str) -> String {
    let mut escaped = text.replace('\\', "\\\\");
    escaped = escaped
        .replace('\r', "\\r")
        .replace('\n', "\\n")
        .replace('\t', "\\t");
    if quote == "'" {
        return escaped.replace('\'', "\\'");
    }
    if quote == "`" {
        return escaped.replace('`', "\\`").replace("${", "\\${");
    }
    escaped.replace('"', "\\\"")
}

pub(super) fn unescape_js_text(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut decoded = String::new();
    let mut index = 0usize;
    while index < chars.len() {
        let char_value = chars[index];
        if char_value != '\\' {
            decoded.push(char_value);
            index += 1;
            continue;
        }
        if index + 1 >= chars.len() {
            decoded.push('\\');
            index += 1;
            continue;
        }
        let escaped = chars[index + 1];
        match escaped {
            '\'' | '"' | '\\' | '/' => decoded.push(escaped),
            'n' => decoded.push('\n'),
            'r' => decoded.push('\r'),
            't' => decoded.push('\t'),
            'b' => decoded.push('\u{0008}'),
            'f' => decoded.push('\u{000c}'),
            'v' => decoded.push('\u{000b}'),
            '0' => decoded.push('\0'),
            '\n' | '\r' => {
                index += 2;
                if escaped == '\r' && index < chars.len() && chars[index] == '\n' {
                    index += 1;
                }
                continue;
            }
            _ => decoded.push(escaped),
        }
        index += 2;
    }
    decoded
}

pub(super) fn normalize_visible_text_for_extraction(raw_text: &str) -> String {
    let mut current = raw_text.to_string();
    loop {
        let trimmed = current.trim();
        if !(trimmed.starts_with('"') && trimmed.ends_with('"')) {
            return current.trim().to_string();
        }
        let decoded = serde_json::from_str::<String>(trimmed);
        match decoded {
            Ok(text) => current = text,
            Err(_error) => return current.trim().to_string(),
        }
    }
}
