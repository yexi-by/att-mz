//! 插件源码 AST 候选扫描与冷索引规则提取。

use rayon::prelude::*;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::Digest;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::LazyLock;

use super::{RuleCandidateOutput, RuleCandidateTextRules};
use crate::native_core::controls::replace_control_sequences;
use crate::native_core::javascript_ast::{
    JavaScriptStringAstContext, JavaScriptStringSpan, parse_javascript_string_spans,
};
use crate::native_core::models::{CompiledRules, NativeTextRules};
use crate::native_core::rules::compile_rules;
use crate::native_core::write_back_plan::{
    candidate_selector_for_span, normalize_visible_text_for_extraction, unescape_js_text,
};

#[derive(Debug, Deserialize)]
pub(super) struct PluginSourceFileInput {
    pub(super) file_name: String,
    pub(super) source: String,
    pub(super) active: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub(super) struct PluginSourceTextRuleInput {
    pub(super) file_name: String,
    #[serde(default)]
    pub(super) selectors: Vec<String>,
    #[serde(default)]
    pub(super) excluded_selectors: Vec<String>,
}

pub(super) struct CompiledRuleCandidateTextRules {
    pub(super) control_rules: CompiledRules,
    pub(super) source_text_required_re: Regex,
    pub(super) source_text_exclusion_profile: String,
    pub(super) strip_wrapping_punctuation_pairs: Vec<(String, String)>,
}

pub(super) struct PluginSourceRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) scanned_file_count: usize,
    pub(super) ignored_file_count: usize,
    pub(super) syntax_error_file_count: usize,
    pub(super) syntax_errors: Vec<Value>,
}

struct PluginSourceFileRuleCandidateScan {
    file_name: String,
    candidates: Vec<RuleCandidateOutput>,
    active: bool,
    syntax_error: bool,
}

#[derive(Debug, Serialize)]
pub(super) struct PluginSourceManagedText {
    pub(super) file_name: String,
    pub(super) selector: String,
    pub(super) text: String,
}

pub(super) enum PluginSourceManagedTextError {
    Stale(String),
    ReviewIncomplete { unreviewed_count: usize },
}

pub(super) static NUMBER_LIKE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[-+]?\d+(?:\.\d+)?$")
        .unwrap_or_else(|error| panic!("内置插件源码数字正则编译失败: {error}"))
});
static RESOURCE_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\.(?:png|jpg|jpeg|webp|gif|ogg|m4a|mp3|wav|json|js|css|ttf|woff2?)$")
        .unwrap_or_else(|error| panic!("内置插件源码资源路径正则编译失败: {error}"))
});
static IDENTIFIER_OR_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[A-Za-z0-9_./:$-]+$")
        .unwrap_or_else(|error| panic!("内置插件源码标识符正则编译失败: {error}"))
});
pub(super) static ENGLISH_ASSET_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:^|[\\/])(?:img|audio|fonts|icon|js|data)[\\/]")
        .unwrap_or_else(|error| panic!("内置英文资源目录正则编译失败: {error}"))
});
pub(super) static ENGLISH_ASSET_EXTENSION_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"\.(?:png|jpe?g|webp|gif|ogg|m4a|mp3|wav|webm|json|js|css|html|ttf|otf|woff2?|rpgmvp|rpgmvo|rpgmvm)$",
    )
    .unwrap_or_else(|error| panic!("内置英文资源扩展名正则编译失败: {error}"))
});
static ENGLISH_THIS_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\bthis\s*(?:\.[A-Za-z_$]|\[)")
        .unwrap_or_else(|error| panic!("内置英文 this 表达式正则编译失败: {error}"))
});
static ENGLISH_CONSOLE_OR_MATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?:console|math)\s*\.")
        .unwrap_or_else(|error| panic!("内置英文协议对象正则编译失败: {error}"))
});
static ENGLISH_VAR_DECL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b(?:var|let|const)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=")
        .unwrap_or_else(|error| panic!("内置英文变量声明正则编译失败: {error}"))
});
static ENGLISH_FUNCTION_DECL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\bfunction(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(")
        .unwrap_or_else(|error| panic!("内置英文函数声明正则编译失败: {error}"))
});
static ENGLISH_RETURN_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\breturn\b.*(?:[;=<>+\-*/]|\b(?:true|false|null|undefined)\b)")
        .unwrap_or_else(|error| panic!("内置英文 return 协议正则编译失败: {error}"))
});
static ENGLISH_DOTTED_CALL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\([^)]*\)")
        .unwrap_or_else(|error| panic!("内置英文链式调用正则编译失败: {error}"))
});
static ENGLISH_OPERATOR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[+\-*/<>=]=?|&&|\|\|")
        .unwrap_or_else(|error| panic!("内置英文运算符正则编译失败: {error}"))
});
static ENGLISH_WORD_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[A-Za-z]{2,}").unwrap_or_else(|error| panic!("内置英文单词正则编译失败: {error}"))
});
static ENGLISH_PATH_ONLY_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[A-Za-z0-9_./\\:-]+$")
        .unwrap_or_else(|error| panic!("内置英文路径正则编译失败: {error}"))
});
static ENGLISH_CAMEL_IDENTIFIER_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[a-z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*$")
        .unwrap_or_else(|error| panic!("内置英文驼峰标识符正则编译失败: {error}"))
});
static ENGLISH_TEMPLATE_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\$\{[^}]+\}")
        .unwrap_or_else(|error| panic!("内置英文模板表达式正则编译失败: {error}"))
});
static ENGLISH_DOLLAR_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\$[A-Za-z_$][A-Za-z0-9_$]*(?:\s*(?:\.|\[|\())")
        .unwrap_or_else(|error| panic!("内置英文美元表达式正则编译失败: {error}"))
});
static ENGLISH_ARROW_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*(?:[{(]|[A-Za-z_$][A-Za-z0-9_$]*\s*[+*/<>=])")
        .unwrap_or_else(|error| panic!("内置英文箭头函数协议正则编译失败: {error}"))
});
static ENGLISH_OBJECT_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\{[^{}]*(?:\b(?:var|let|const|return|function|if|for|while)\b|[A-Za-z_$][A-Za-z0-9_$]*\s*:|[A-Za-z_$][A-Za-z0-9_$]*\s*=|;)[^{}]*\}")
        .unwrap_or_else(|error| panic!("内置英文对象协议正则编译失败: {error}"))
});
static ENGLISH_STATEMENT_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:\b(?:return|var|let|const|throw|break|continue)\b|[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[[^\]]+\])*\s*(?:[-+*/]?=)|\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\([^)]*\))[^.;!?]*;")
        .unwrap_or_else(|error| panic!("内置英文语句协议正则编译失败: {error}"))
});

pub(super) fn scan_plugin_source_rule_candidates(
    files: &[PluginSourceFileInput],
    text_rules: RuleCandidateTextRules,
) -> Result<PluginSourceRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let mut file_refs: Vec<&PluginSourceFileInput> = files.iter().collect();
    file_refs.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let file_scans = file_refs
        .par_iter()
        .map(|file| scan_plugin_source_rule_candidate_file(file, &compiled_rules))
        .collect::<Result<Vec<_>, String>>()?;
    let scanned_file_count = file_scans.iter().filter(|scan| !scan.syntax_error).count();
    let ignored_file_count = file_scans
        .iter()
        .filter(|scan| !scan.syntax_error && !scan.active)
        .count();
    let syntax_error_file_count = file_scans.iter().filter(|scan| scan.syntax_error).count();
    let syntax_errors = file_scans
        .iter()
        .filter(|scan| scan.syntax_error)
        .map(|scan| {
            json!({
                "file": scan.file_name,
                "active": scan.active,
                "syntax_error": "原生 AST 解析报告 JS 语法错误"
            })
        })
        .collect();
    let candidates = file_scans
        .into_iter()
        .flat_map(|scan| scan.candidates)
        .collect();
    Ok(PluginSourceRuleCandidateScan {
        candidates,
        scanned_file_count,
        ignored_file_count,
        syntax_error_file_count,
        syntax_errors,
    })
}

pub(super) fn collect_plugin_source_managed_texts(
    files: &[PluginSourceFileInput],
    rules: &[PluginSourceTextRuleInput],
    text_rules: RuleCandidateTextRules,
) -> Result<Vec<PluginSourceManagedText>, PluginSourceManagedTextError> {
    if rules.is_empty() {
        return Ok(Vec::new());
    }
    let scan = scan_plugin_source_rule_candidates(files, text_rules)
        .map_err(PluginSourceManagedTextError::Stale)?;
    let candidates_by_file_selector = scan
        .candidates
        .into_iter()
        .map(|candidate| {
            let selector = candidate
                .selector
                .clone()
                .unwrap_or_else(|| candidate.rule_key.clone());
            ((candidate.source_file.clone(), selector), candidate)
        })
        .collect::<BTreeMap<_, _>>();
    let file_hashes = files
        .iter()
        .map(|file| (file.file_name.as_str(), sha256_text(&file.source)))
        .collect::<BTreeMap<_, _>>();
    let active_files = files
        .iter()
        .filter(|file| file.active)
        .map(|file| file.file_name.as_str())
        .collect::<BTreeSet<_>>();

    let mut managed_texts = Vec::new();
    let mut reviewed_selectors_by_file: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for rule in rules {
        if !file_hashes.contains_key(rule.file_name.as_str()) {
            return Err(PluginSourceManagedTextError::Stale(format!(
                "插件源码规则已过期: {}: 插件源码文件不存在，请重新导出并导入插件源码规则",
                rule.file_name
            )));
        }
        if !active_files.contains(rule.file_name.as_str()) {
            return Err(PluginSourceManagedTextError::Stale(format!(
                "插件源码规则已过期: {}: 插件源码文件未在 plugins.js 中启用，请重新导出并导入插件源码规则",
                rule.file_name
            )));
        }
        for selector in rule.selectors.iter().chain(rule.excluded_selectors.iter()) {
            if !candidates_by_file_selector
                .contains_key(&(rule.file_name.clone(), selector.clone()))
            {
                return Err(PluginSourceManagedTextError::Stale(format!(
                    "插件源码规则已过期: {}: 插件源码 selector 已无法命中当前 AST 地图，请重新导出并导入插件源码规则",
                    rule.file_name
                )));
            }
        }
        let reviewed_selectors = reviewed_selectors_by_file
            .entry(rule.file_name.clone())
            .or_default();
        reviewed_selectors.extend(rule.selectors.iter().cloned());
        reviewed_selectors.extend(rule.excluded_selectors.iter().cloned());
        for selector in &rule.selectors {
            let Some(candidate) =
                candidates_by_file_selector.get(&(rule.file_name.clone(), selector.clone()))
            else {
                continue;
            };
            managed_texts.push(PluginSourceManagedText {
                file_name: rule.file_name.clone(),
                selector: selector.clone(),
                text: candidate.original_text.clone(),
            });
        }
    }
    let unreviewed_count = candidates_by_file_selector
        .iter()
        .filter(|((file_name, selector), candidate)| {
            candidate.active == Some(true)
                && !reviewed_selectors_by_file
                    .get(file_name)
                    .is_some_and(|reviewed_selectors| reviewed_selectors.contains(selector))
        })
        .count();
    if unreviewed_count > 0 {
        return Err(PluginSourceManagedTextError::ReviewIncomplete { unreviewed_count });
    }
    managed_texts.sort_by(|left, right| {
        left.file_name
            .cmp(&right.file_name)
            .then_with(|| left.selector.cmp(&right.selector))
    });
    Ok(managed_texts)
}

pub(super) fn compile_rule_candidate_text_rules(
    text_rules: RuleCandidateTextRules,
) -> Result<CompiledRuleCandidateTextRules, String> {
    let source_text_exclusion_profile = match text_rules.source_text_exclusion_profile.as_str() {
        "none" | "english_protocol_noise" => text_rules.source_text_exclusion_profile,
        unknown => {
            return Err(format!("插件源码候选源文排除模式无效: {unknown}"));
        }
    };
    let control_rules = compile_rules(NativeTextRules {
        custom_placeholder_rules: text_rules.custom_placeholder_rules,
        structured_placeholder_rules: text_rules.structured_placeholder_rules,
        source_residual_allowed_chars: Vec::new(),
        source_residual_allowed_tail_chars: Vec::new(),
        source_residual_segment_pattern: r"[\s\S]+".to_string(),
        source_residual_label: "源文".to_string(),
        allowed_source_residual_terms: Vec::new(),
        source_residual_terms_ignore_case: false,
        source_residual_detection_profile: "japanese_strict".to_string(),
        english_source_copy_min_words: 4,
        english_source_copy_min_letters: 12,
        line_width_count_pattern: r"\S".to_string(),
        residual_escape_sequence_pattern: r"\\[nrt]".to_string(),
        long_text_line_width_limit: 999,
    })?;
    let source_text_required_re = Regex::new(&text_rules.source_text_required_pattern)
        .map_err(|error| format!("插件源码源文识别正则无效: {error}"))?;
    Ok(CompiledRuleCandidateTextRules {
        control_rules,
        source_text_required_re,
        source_text_exclusion_profile,
        strip_wrapping_punctuation_pairs: text_rules.strip_wrapping_punctuation_pairs,
    })
}

fn scan_plugin_source_rule_candidate_file(
    file: &PluginSourceFileInput,
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<PluginSourceFileRuleCandidateScan, String> {
    let scan = parse_javascript_string_spans(&file.source)
        .map_err(|error| format!("{} JS AST 解析失败: {error}", file.file_name))?;
    if scan.has_error {
        return Ok(PluginSourceFileRuleCandidateScan {
            file_name: file.file_name.clone(),
            candidates: Vec::new(),
            active: file.active,
            syntax_error: true,
        });
    }
    let file_hash = sha256_text(&file.source);
    let newline_indexes = collect_newline_indexes(&file.source);
    let mut candidates = Vec::new();
    for span in scan.spans {
        if let Some(candidate) = plugin_source_candidate_from_span(
            file,
            &span,
            &file_hash,
            &newline_indexes,
            text_rules,
        )? {
            candidates.push(candidate);
        }
    }
    Ok(PluginSourceFileRuleCandidateScan {
        file_name: file.file_name.clone(),
        candidates,
        active: file.active,
        syntax_error: false,
    })
}

fn plugin_source_candidate_from_span(
    file: &PluginSourceFileInput,
    span: &JavaScriptStringSpan,
    file_hash: &str,
    newline_indexes: &[usize],
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<Option<RuleCandidateOutput>, String> {
    let raw_text = file
        .source
        .get(span.content_start_byte_index..span.content_end_byte_index)
        .ok_or_else(|| format!("插件源码字符串范围无效: {}", file.file_name))?;
    let text = normalize_visible_text_for_extraction(&unescape_js_text(raw_text));
    if text.is_empty() || !should_translate_plugin_source_text(&text, text_rules)? {
        return Ok(None);
    }
    let api = span.ast_context.call_name.clone();
    let key = span.ast_context.property_key.clone();
    let structural_flags = plugin_source_text_structural_flags(&text);
    let confidence =
        plugin_source_candidate_confidence(&text, &api, &key, &span.ast_context, &structural_flags);
    let selector = candidate_selector_for_span(span.start_index, span.end_index, raw_text);
    let location_path = format!("js/plugins/{}/{}", file.file_name, selector);
    let line = line_number_for_index(newline_indexes, span.start_index);
    Ok(Some(RuleCandidateOutput {
        domain: "plugin_source".to_string(),
        location_path,
        rule_key: selector.clone(),
        original_text: text.clone(),
        source_file: file.file_name.clone(),
        file: Some(file.file_name.clone()),
        json_path: None,
        source_text: None,
        field_name: None,
        sibling_field_names: None,
        parent_object_keys: None,
        selector: Some(selector),
        text: Some(text),
        raw_text: Some(raw_text.to_string()),
        quote: Some(span.quote.clone()),
        line: Some(line),
        start_index: Some(span.start_index),
        end_index: Some(span.end_index),
        content_start_index: Some(span.content_start_index),
        content_end_index: Some(span.content_end_index),
        context: Some(plugin_source_candidate_context(&api, &key)),
        api: Some(api),
        key: Some(key),
        ast_context: Some(plugin_source_ast_context_json(&span.ast_context)),
        active: Some(file.active),
        confidence: Some(confidence),
        structural_flags: Some(structural_flags),
        file_hash: Some(file_hash.to_string()),
    }))
}

pub(super) fn should_translate_plugin_source_text(
    text: &str,
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<bool, String> {
    let normalized_text =
        normalize_extraction_text(text, &text_rules.strip_wrapping_punctuation_pairs);
    if normalized_text.is_empty() {
        return Ok(false);
    }
    if text_rules.source_text_exclusion_profile == "english_protocol_noise"
        && is_english_protocol_noise_text(&normalized_text, &text_rules.control_rules)?
    {
        return Ok(false);
    }
    let detection_text =
        replace_control_sequences(&normalized_text, &text_rules.control_rules, |_span| {
            String::new()
        })?;
    if detection_text.is_empty() {
        return Ok(false);
    }
    Ok(text_rules.source_text_required_re.is_match(&detection_text))
}

pub(super) fn normalize_extraction_text(text: &str, wrapping_pairs: &[(String, String)]) -> String {
    let mut normalized_text = text.trim().to_string();
    for (left, right) in wrapping_pairs {
        if normalized_text.starts_with(left) && normalized_text.ends_with(right) {
            normalized_text = normalized_text[left.len()..normalized_text.len() - right.len()]
                .trim()
                .to_string();
        }
    }
    normalized_text
}

fn is_english_protocol_noise_text(
    text: &str,
    control_rules: &CompiledRules,
) -> Result<bool, String> {
    let stripped = replace_control_sequences(text, control_rules, |_span| String::new())?
        .trim()
        .to_string();
    if stripped.is_empty() {
        return Ok(true);
    }
    let lowered = stripped.to_ascii_lowercase();
    if matches!(
        lowered.as_str(),
        "true" | "false" | "null" | "undefined" | "gamefont"
    ) {
        return Ok(true);
    }
    Ok(NUMBER_LIKE_RE.is_match(&stripped)
        || ENGLISH_ASSET_PATH_RE.is_match(&lowered)
        || ENGLISH_ASSET_EXTENSION_RE.is_match(&lowered)
        || ENGLISH_THIS_EXPR_RE.is_match(&stripped)
        || ENGLISH_CONSOLE_OR_MATH_RE.is_match(&stripped)
        || ENGLISH_VAR_DECL_RE.is_match(&stripped)
        || ENGLISH_FUNCTION_DECL_RE.is_match(&stripped)
        || ENGLISH_RETURN_PROTOCOL_RE.is_match(&stripped)
        || ENGLISH_DOTTED_CALL_RE.is_match(&stripped)
        || (ENGLISH_OPERATOR_RE.is_match(&stripped)
            && ENGLISH_WORD_RE.find_iter(&stripped).count() < 2)
        || ((stripped.contains('/') || stripped.contains('\\'))
            && ENGLISH_PATH_ONLY_RE.is_match(&stripped))
        || ENGLISH_CAMEL_IDENTIFIER_RE.is_match(&stripped)
        || looks_like_english_script_punctuation(&stripped))
}

fn looks_like_english_script_punctuation(text: &str) -> bool {
    ENGLISH_TEMPLATE_EXPR_RE.is_match(text)
        || ENGLISH_DOLLAR_EXPR_RE.is_match(text)
        || ENGLISH_ARROW_PROTOCOL_RE.is_match(text)
        || ENGLISH_OBJECT_PROTOCOL_RE.is_match(text)
        || ENGLISH_STATEMENT_PROTOCOL_RE.is_match(text)
}

fn plugin_source_text_structural_flags(text: &str) -> Vec<String> {
    let mut flags = Vec::new();
    let lowered_text = text.to_ascii_lowercase();
    if NUMBER_LIKE_RE.is_match(text) {
        flags.push("number_like".to_string());
    }
    if RESOURCE_PATH_RE.is_match(&lowered_text) {
        flags.push("resource_path_like".to_string());
    }
    if IDENTIFIER_OR_PATH_RE.is_match(text) && (text.contains('_') || text.contains('/')) {
        flags.push("identifier_or_path_like".to_string());
    }
    flags
}

fn plugin_source_candidate_confidence(
    text: &str,
    api: &str,
    key: &str,
    ast_context: &JavaScriptStringAstContext,
    structural_flags: &[String],
) -> String {
    if structural_flags
        .iter()
        .any(|flag| flag == "resource_path_like" || flag == "number_like")
    {
        return "weak".to_string();
    }
    if is_strong_plugin_source_call(api) || is_strong_plugin_source_key(key) {
        return "strong".to_string();
    }
    if !ast_context.return_function_name.is_empty()
        || !ast_context.assignment_name.is_empty()
        || !ast_context.property_path.is_empty()
    {
        return "medium".to_string();
    }
    if text.chars().count() >= 8
        && !structural_flags
            .iter()
            .any(|flag| flag == "identifier_or_path_like")
    {
        return "medium".to_string();
    }
    "weak".to_string()
}

fn is_strong_plugin_source_key(key: &str) -> bool {
    matches!(
        key,
        "body"
            | "caption"
            | "description"
            | "help"
            | "helpLines"
            | "label"
            | "longDescription"
            | "message"
            | "name"
            | "nickName"
            | "param1"
            | "param2"
            | "shortDescription"
            | "stanceDescription"
            | "text"
            | "title"
    )
}

fn is_strong_plugin_source_call(api: &str) -> bool {
    [
        "addCommand",
        "addText",
        "drawText",
        "drawTextEx",
        "setText",
        "$gameMessage.add",
    ]
    .iter()
    .any(|suffix| api == *suffix || api.ends_with(suffix))
}

fn plugin_source_candidate_context(api: &str, key: &str) -> String {
    if !api.is_empty() {
        return format!("call:{api}");
    }
    if !key.is_empty() {
        return format!("property:{key}");
    }
    "literal".to_string()
}

fn plugin_source_ast_context_json(context: &JavaScriptStringAstContext) -> Value {
    json!({
        "node_kind": context.node_kind,
        "property_key": context.property_key,
        "property_path": context.property_path,
        "call_name": context.call_name,
        "call_argument_index": context.call_argument_index,
        "return_function_name": context.return_function_name,
        "assignment_name": context.assignment_name
    })
}

fn collect_newline_indexes(source: &str) -> Vec<usize> {
    source
        .chars()
        .enumerate()
        .filter_map(|(index, char_value)| {
            if char_value == '\n' {
                Some(index)
            } else {
                None
            }
        })
        .collect()
}

fn line_number_for_index(newline_indexes: &[usize], index: usize) -> usize {
    newline_indexes.partition_point(|newline_index| *newline_index <= index) + 1
}

pub(super) fn sha256_text(text: &str) -> String {
    let mut hasher = sha2::Sha256::new();
    hasher.update(text.as_bytes());
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
