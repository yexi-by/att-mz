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

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(super) struct PluginSourceStaleReason {
    pub(super) code: String,
    pub(super) message: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(super) struct PluginSourceSelectorFact {
    pub(super) file_name: String,
    pub(super) selector: String,
    pub(super) role: String,
    pub(super) active: bool,
    pub(super) file_hash: String,
    pub(super) source_text_hash: String,
    pub(super) stale_reason: Option<PluginSourceStaleReason>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(super) struct PluginSourceReviewSummary {
    pub(super) total_selector_count: usize,
    pub(super) translated_selector_count: usize,
    pub(super) excluded_selector_count: usize,
    pub(super) filtered_selector_count: usize,
    pub(super) reviewed_selector_count: usize,
    pub(super) stale_selector_count: usize,
    pub(super) active_candidate_count: usize,
    pub(super) unreviewed_selector_count: usize,
    pub(super) review_required: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(super) struct PluginSourceRiskThresholds {
    pub(super) strong_context_text_count: usize,
    pub(super) risk_score: usize,
    pub(super) files_score_ge_250: usize,
    pub(super) single_file_score: usize,
    pub(super) single_file_strong_context_text_count: usize,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(super) struct PluginSourceRiskSummary {
    pub(super) high_risk: bool,
    pub(super) risk_score: usize,
    pub(super) strong_context_text_count: usize,
    pub(super) medium_confidence_text_count: usize,
    pub(super) scanned_file_count: usize,
    pub(super) ignored_file_count: usize,
    pub(super) read_error_file_count: usize,
    pub(super) syntax_error_file_count: usize,
    pub(super) files_score_ge_250: usize,
    pub(super) max_file_score: usize,
    pub(super) thresholds: PluginSourceRiskThresholds,
}

pub(super) struct PluginSourceRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) selector_facts: Vec<PluginSourceSelectorFact>,
    pub(super) review_summary: PluginSourceReviewSummary,
    pub(super) risk_summary: PluginSourceRiskSummary,
    pub(super) scope_hash: String,
    pub(super) scanned_file_count: usize,
    pub(super) ignored_file_count: usize,
    pub(super) syntax_error_file_count: usize,
    pub(super) syntax_errors: Vec<Value>,
}

struct PluginSourceFileRuleCandidateScan {
    file_name: String,
    candidates: Vec<RuleCandidateOutput>,
    filtered_selectors: BTreeMap<String, String>,
    active: bool,
    syntax_error: bool,
}

enum PluginSourceSpanCandidateDecision {
    Candidate(Box<RuleCandidateOutput>),
    Filtered {
        selector: String,
        source_text_hash: String,
    },
}

#[derive(Debug, Serialize)]
pub(super) struct PluginSourceManagedText {
    pub(super) file_name: String,
    pub(super) selector: String,
    pub(super) text: String,
    pub(super) raw_text: String,
    pub(super) quote: String,
    pub(super) line: usize,
    pub(super) start_index: usize,
    pub(super) end_index: usize,
    pub(super) content_start_index: usize,
    pub(super) content_end_index: usize,
}

pub(super) enum PluginSourceManagedTextError {
    Stale(String),
    ReviewIncomplete { unreviewed_count: usize },
    InvalidCandidate(String),
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
const PLUGIN_SOURCE_ROLE_TRANSLATED: &str = "translated";
const PLUGIN_SOURCE_ROLE_EXCLUDED: &str = "excluded";
const PLUGIN_SOURCE_ROLE_FILTERED: &str = "filtered";
const PLUGIN_SOURCE_STRONG_CONTEXT_THRESHOLD: usize = 300;
const PLUGIN_SOURCE_RISK_SCORE_THRESHOLD: usize = 2000;
const PLUGIN_SOURCE_FILES_SCORE_GE_250_THRESHOLD: usize = 3;
const PLUGIN_SOURCE_SINGLE_FILE_SCORE_THRESHOLD: usize = 300;
const PLUGIN_SOURCE_SINGLE_FILE_STRONG_CONTEXT_THRESHOLD: usize = 80;

pub(super) fn scan_plugin_source_rule_candidates(
    files: &[PluginSourceFileInput],
    text_rules: RuleCandidateTextRules,
) -> Result<PluginSourceRuleCandidateScan, String> {
    scan_plugin_source_rule_candidates_with_rules(files, &[], text_rules, 0)
}

pub(super) fn scan_plugin_source_rule_candidates_with_rules(
    files: &[PluginSourceFileInput],
    rules: &[PluginSourceTextRuleInput],
    text_rules: RuleCandidateTextRules,
    read_error_file_count: usize,
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
    let filtered_selectors = file_scans
        .iter()
        .flat_map(|scan| {
            scan.filtered_selectors
                .iter()
                .map(|(selector, source_text_hash)| {
                    (
                        (scan.file_name.clone(), selector.clone()),
                        source_text_hash.clone(),
                    )
                })
        })
        .collect::<BTreeMap<_, _>>();
    let candidates = file_scans
        .into_iter()
        .flat_map(|scan| scan.candidates)
        .collect::<Vec<_>>();
    let selector_facts =
        build_plugin_source_selector_facts(files, rules, &candidates, &filtered_selectors);
    let risk_summary = build_plugin_source_risk_summary(
        &candidates,
        scanned_file_count,
        ignored_file_count,
        syntax_error_file_count,
        read_error_file_count,
    );
    let review_summary = build_plugin_source_review_summary(&selector_facts, &risk_summary);
    let scope_hash = plugin_source_selector_scope_hash(&selector_facts);
    Ok(PluginSourceRuleCandidateScan {
        candidates,
        selector_facts,
        review_summary,
        risk_summary,
        scope_hash,
        scanned_file_count,
        ignored_file_count,
        syntax_error_file_count,
        syntax_errors,
    })
}

fn build_plugin_source_selector_facts(
    files: &[PluginSourceFileInput],
    rules: &[PluginSourceTextRuleInput],
    candidates: &[RuleCandidateOutput],
    filtered_selectors: &BTreeMap<(String, String), String>,
) -> Vec<PluginSourceSelectorFact> {
    let files_by_name = files
        .iter()
        .map(|file| (file.file_name.as_str(), file))
        .collect::<BTreeMap<_, _>>();
    let file_hashes = files
        .iter()
        .map(|file| (file.file_name.as_str(), sha256_text(&file.source)))
        .collect::<BTreeMap<_, _>>();
    let candidates_by_file_selector = candidates
        .iter()
        .filter_map(|candidate| {
            let selector = candidate.selector.as_ref()?;
            Some((
                (candidate.source_file.as_str(), selector.as_str()),
                candidate,
            ))
        })
        .collect::<BTreeMap<_, _>>();
    let mut reviewed_selectors = BTreeSet::new();
    let mut facts = BTreeMap::new();

    for rule in rules {
        for selector in &rule.selectors {
            reviewed_selectors.insert((rule.file_name.as_str(), selector.as_str()));
            let fact = plugin_source_selector_fact_for_rule_selector(
                &rule.file_name,
                selector,
                PLUGIN_SOURCE_ROLE_TRANSLATED,
                &files_by_name,
                &file_hashes,
                &candidates_by_file_selector,
                filtered_selectors,
            );
            facts.insert(
                (
                    fact.file_name.clone(),
                    fact.selector.clone(),
                    fact.role.clone(),
                ),
                fact,
            );
        }
        for selector in &rule.excluded_selectors {
            reviewed_selectors.insert((rule.file_name.as_str(), selector.as_str()));
            let fact = plugin_source_selector_fact_for_rule_selector(
                &rule.file_name,
                selector,
                PLUGIN_SOURCE_ROLE_EXCLUDED,
                &files_by_name,
                &file_hashes,
                &candidates_by_file_selector,
                filtered_selectors,
            );
            facts.insert(
                (
                    fact.file_name.clone(),
                    fact.selector.clone(),
                    fact.role.clone(),
                ),
                fact,
            );
        }
    }

    for candidate in candidates {
        let Some(selector) = candidate.selector.as_deref() else {
            continue;
        };
        if reviewed_selectors.contains(&(candidate.source_file.as_str(), selector)) {
            continue;
        }
        let file_hash = candidate
            .file_hash
            .clone()
            .or_else(|| file_hashes.get(candidate.source_file.as_str()).cloned())
            .unwrap_or_default();
        let fact = PluginSourceSelectorFact {
            file_name: candidate.source_file.clone(),
            selector: selector.to_string(),
            role: PLUGIN_SOURCE_ROLE_FILTERED.to_string(),
            active: candidate.active.unwrap_or(false),
            file_hash,
            source_text_hash: sha256_text(&candidate.original_text),
            stale_reason: None,
        };
        facts.insert(
            (
                fact.file_name.clone(),
                fact.selector.clone(),
                fact.role.clone(),
            ),
            fact,
        );
    }

    facts.into_values().collect()
}

fn plugin_source_selector_fact_for_rule_selector(
    file_name: &str,
    selector: &str,
    role: &str,
    files_by_name: &BTreeMap<&str, &PluginSourceFileInput>,
    file_hashes: &BTreeMap<&str, String>,
    candidates_by_file_selector: &BTreeMap<(&str, &str), &RuleCandidateOutput>,
    filtered_selectors: &BTreeMap<(String, String), String>,
) -> PluginSourceSelectorFact {
    let Some(file) = files_by_name.get(file_name).copied() else {
        return PluginSourceSelectorFact {
            file_name: file_name.to_string(),
            selector: selector.to_string(),
            role: role.to_string(),
            active: false,
            file_hash: String::new(),
            source_text_hash: String::new(),
            stale_reason: Some(plugin_source_stale_reason(
                "file_missing",
                "插件源码文件不存在或不是 js/plugins 直接文件",
            )),
        };
    };
    let file_hash = file_hashes.get(file_name).cloned().unwrap_or_default();
    if !file.active {
        return PluginSourceSelectorFact {
            file_name: file_name.to_string(),
            selector: selector.to_string(),
            role: role.to_string(),
            active: false,
            file_hash,
            source_text_hash: candidates_by_file_selector
                .get(&(file_name, selector))
                .map(|candidate| sha256_text(&candidate.original_text))
                .or_else(|| {
                    filtered_selectors
                        .get(&(file_name.to_string(), selector.to_string()))
                        .cloned()
                })
                .unwrap_or_default(),
            stale_reason: Some(plugin_source_stale_reason(
                "file_inactive",
                "插件源码文件未在 plugins.js 中启用",
            )),
        };
    }
    if let Some(candidate) = candidates_by_file_selector.get(&(file_name, selector)) {
        return PluginSourceSelectorFact {
            file_name: file_name.to_string(),
            selector: selector.to_string(),
            role: role.to_string(),
            active: candidate.active.unwrap_or(file.active),
            file_hash: candidate
                .file_hash
                .clone()
                .unwrap_or_else(|| file_hash.clone()),
            source_text_hash: sha256_text(&candidate.original_text),
            stale_reason: None,
        };
    }
    if let Some(source_text_hash) =
        filtered_selectors.get(&(file_name.to_string(), selector.to_string()))
    {
        return PluginSourceSelectorFact {
            file_name: file_name.to_string(),
            selector: selector.to_string(),
            role: role.to_string(),
            active: file.active,
            file_hash,
            source_text_hash: source_text_hash.clone(),
            stale_reason: Some(plugin_source_stale_reason(
                "selector_filtered",
                "插件源码 selector 被当前文本规则过滤",
            )),
        };
    }
    PluginSourceSelectorFact {
        file_name: file_name.to_string(),
        selector: selector.to_string(),
        role: role.to_string(),
        active: file.active,
        file_hash,
        source_text_hash: String::new(),
        stale_reason: Some(plugin_source_stale_reason(
            "selector_missing",
            "插件源码 selector 已无法命中当前 AST 地图",
        )),
    }
}

fn plugin_source_stale_reason(code: &str, message: &str) -> PluginSourceStaleReason {
    PluginSourceStaleReason {
        code: code.to_string(),
        message: message.to_string(),
    }
}

fn build_plugin_source_risk_summary(
    candidates: &[RuleCandidateOutput],
    scanned_file_count: usize,
    ignored_file_count: usize,
    syntax_error_file_count: usize,
    read_error_file_count: usize,
) -> PluginSourceRiskSummary {
    let mut file_scores: BTreeMap<&str, usize> = BTreeMap::new();
    let mut file_strong_counts: BTreeMap<&str, usize> = BTreeMap::new();
    let mut strong_context_text_count = 0;
    let mut medium_confidence_text_count = 0;
    for candidate in candidates {
        if candidate.active != Some(true) {
            continue;
        }
        match candidate.confidence.as_deref() {
            Some("strong") => {
                strong_context_text_count += 1;
                *file_scores
                    .entry(candidate.source_file.as_str())
                    .or_default() += 3;
                *file_strong_counts
                    .entry(candidate.source_file.as_str())
                    .or_default() += 1;
            }
            Some("medium") => {
                medium_confidence_text_count += 1;
                *file_scores
                    .entry(candidate.source_file.as_str())
                    .or_default() += 1;
            }
            _ => {}
        }
    }
    let risk_score = strong_context_text_count * 3 + medium_confidence_text_count;
    let files_score_ge_250 = file_scores
        .values()
        .filter(|file_score| **file_score >= 250)
        .count();
    let max_file_score = file_scores.values().copied().max().unwrap_or(0);
    let high_risk = strong_context_text_count >= PLUGIN_SOURCE_STRONG_CONTEXT_THRESHOLD
        || risk_score >= PLUGIN_SOURCE_RISK_SCORE_THRESHOLD
        || files_score_ge_250 >= PLUGIN_SOURCE_FILES_SCORE_GE_250_THRESHOLD
        || file_scores.iter().any(|(file_name, file_score)| {
            *file_score >= PLUGIN_SOURCE_SINGLE_FILE_SCORE_THRESHOLD
                && file_strong_counts.get(file_name).copied().unwrap_or(0)
                    >= PLUGIN_SOURCE_SINGLE_FILE_STRONG_CONTEXT_THRESHOLD
        });
    PluginSourceRiskSummary {
        high_risk,
        risk_score,
        strong_context_text_count,
        medium_confidence_text_count,
        scanned_file_count,
        ignored_file_count,
        read_error_file_count,
        syntax_error_file_count,
        files_score_ge_250,
        max_file_score,
        thresholds: PluginSourceRiskThresholds {
            strong_context_text_count: PLUGIN_SOURCE_STRONG_CONTEXT_THRESHOLD,
            risk_score: PLUGIN_SOURCE_RISK_SCORE_THRESHOLD,
            files_score_ge_250: PLUGIN_SOURCE_FILES_SCORE_GE_250_THRESHOLD,
            single_file_score: PLUGIN_SOURCE_SINGLE_FILE_SCORE_THRESHOLD,
            single_file_strong_context_text_count:
                PLUGIN_SOURCE_SINGLE_FILE_STRONG_CONTEXT_THRESHOLD,
        },
    }
}

fn build_plugin_source_review_summary(
    selector_facts: &[PluginSourceSelectorFact],
    risk_summary: &PluginSourceRiskSummary,
) -> PluginSourceReviewSummary {
    let translated_selector_count = selector_facts
        .iter()
        .filter(|fact| fact.role == PLUGIN_SOURCE_ROLE_TRANSLATED)
        .count();
    let excluded_selector_count = selector_facts
        .iter()
        .filter(|fact| fact.role == PLUGIN_SOURCE_ROLE_EXCLUDED)
        .count();
    let filtered_selector_count = selector_facts
        .iter()
        .filter(|fact| fact.role == PLUGIN_SOURCE_ROLE_FILTERED)
        .count();
    let stale_selector_count = selector_facts
        .iter()
        .filter(|fact| fact.stale_reason.is_some())
        .count();
    let unreviewed_selector_count = selector_facts
        .iter()
        .filter(|fact| {
            fact.role == PLUGIN_SOURCE_ROLE_FILTERED && fact.active && fact.stale_reason.is_none()
        })
        .count();
    let reviewed_selector_count = translated_selector_count + excluded_selector_count;
    PluginSourceReviewSummary {
        total_selector_count: selector_facts.len(),
        translated_selector_count,
        excluded_selector_count,
        filtered_selector_count,
        reviewed_selector_count,
        stale_selector_count,
        active_candidate_count: selector_facts
            .iter()
            .filter(|fact| fact.active && fact.stale_reason.is_none())
            .count(),
        unreviewed_selector_count,
        review_required: risk_summary.high_risk || reviewed_selector_count > 0,
    }
}

fn plugin_source_selector_scope_hash(selector_facts: &[PluginSourceSelectorFact]) -> String {
    let mut lines = vec!["plugin_source_selector_facts:v1".to_string()];
    for fact in selector_facts {
        let stale_code = fact
            .stale_reason
            .as_ref()
            .map(|reason| reason.code.as_str())
            .unwrap_or("");
        lines.push(format!(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}",
            fact.file_name,
            fact.selector,
            fact.role,
            fact.active,
            fact.file_hash,
            fact.source_text_hash,
            stale_code
        ));
    }
    sha256_text(&lines.join("\n"))
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
            managed_texts.push(plugin_source_managed_text_from_candidate(
                &rule.file_name,
                selector,
                candidate,
            )?);
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

fn plugin_source_managed_text_from_candidate(
    file_name: &str,
    selector: &str,
    candidate: &RuleCandidateOutput,
) -> Result<PluginSourceManagedText, PluginSourceManagedTextError> {
    Ok(PluginSourceManagedText {
        file_name: file_name.to_string(),
        selector: selector.to_string(),
        text: candidate.original_text.clone(),
        raw_text: required_plugin_source_candidate_string(
            candidate.raw_text.as_deref(),
            file_name,
            selector,
            "raw_text",
        )?,
        quote: required_plugin_source_candidate_string(
            candidate.quote.as_deref(),
            file_name,
            selector,
            "quote",
        )?,
        line: required_plugin_source_candidate_usize(candidate.line, file_name, selector, "line")?,
        start_index: required_plugin_source_candidate_usize(
            candidate.start_index,
            file_name,
            selector,
            "start_index",
        )?,
        end_index: required_plugin_source_candidate_usize(
            candidate.end_index,
            file_name,
            selector,
            "end_index",
        )?,
        content_start_index: required_plugin_source_candidate_usize(
            candidate.content_start_index,
            file_name,
            selector,
            "content_start_index",
        )?,
        content_end_index: required_plugin_source_candidate_usize(
            candidate.content_end_index,
            file_name,
            selector,
            "content_end_index",
        )?,
    })
}

fn required_plugin_source_candidate_string(
    value: Option<&str>,
    file_name: &str,
    selector: &str,
    field_name: &str,
) -> Result<String, PluginSourceManagedTextError> {
    value
        .map(str::to_string)
        .ok_or_else(|| plugin_source_candidate_contract_error(file_name, selector, field_name))
}

fn required_plugin_source_candidate_usize(
    value: Option<usize>,
    file_name: &str,
    selector: &str,
    field_name: &str,
) -> Result<usize, PluginSourceManagedTextError> {
    value.ok_or_else(|| plugin_source_candidate_contract_error(file_name, selector, field_name))
}

fn plugin_source_candidate_contract_error(
    file_name: &str,
    selector: &str,
    field_name: &str,
) -> PluginSourceManagedTextError {
    PluginSourceManagedTextError::InvalidCandidate(format!(
        "插件源码候选缺少必需字段 {field_name}: {file_name}/{selector}"
    ))
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
            filtered_selectors: BTreeMap::new(),
            active: file.active,
            syntax_error: true,
        });
    }
    let file_hash = sha256_text(&file.source);
    let newline_indexes = collect_newline_indexes(&file.source);
    let mut candidates = Vec::new();
    let mut filtered_selectors = BTreeMap::new();
    for span in scan.spans {
        match plugin_source_candidate_from_span(
            file,
            &span,
            &file_hash,
            &newline_indexes,
            text_rules,
        )? {
            PluginSourceSpanCandidateDecision::Candidate(candidate) => {
                candidates.push(*candidate);
            }
            PluginSourceSpanCandidateDecision::Filtered {
                selector,
                source_text_hash,
            } => {
                filtered_selectors.insert(selector, source_text_hash);
            }
        }
    }
    Ok(PluginSourceFileRuleCandidateScan {
        file_name: file.file_name.clone(),
        candidates,
        filtered_selectors,
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
) -> Result<PluginSourceSpanCandidateDecision, String> {
    let raw_text = file
        .source
        .get(span.content_start_byte_index..span.content_end_byte_index)
        .ok_or_else(|| format!("插件源码字符串范围无效: {}", file.file_name))?;
    let text = normalize_visible_text_for_extraction(&unescape_js_text(raw_text));
    let selector = candidate_selector_for_span(span.start_index, span.end_index, raw_text);
    if text.is_empty() || !should_translate_plugin_source_text(&text, text_rules)? {
        return Ok(PluginSourceSpanCandidateDecision::Filtered {
            selector,
            source_text_hash: sha256_text(&text),
        });
    }
    let api = span.ast_context.call_name.clone();
    let key = span.ast_context.property_key.clone();
    let structural_flags = plugin_source_text_structural_flags(&text);
    let confidence =
        plugin_source_candidate_confidence(&text, &api, &key, &span.ast_context, &structural_flags);
    let location_path = format!("js/plugins/{}/{}", file.file_name, selector);
    let line = line_number_for_index(newline_indexes, span.start_index);
    Ok(PluginSourceSpanCandidateDecision::Candidate(Box::new(
        RuleCandidateOutput {
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
        },
    )))
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

#[cfg(test)]
mod tests {
    use super::{
        PluginSourceFileInput, PluginSourceManagedTextError, PluginSourceTextRuleInput,
        collect_plugin_source_managed_texts, plugin_source_managed_text_from_candidate,
        scan_plugin_source_rule_candidates,
    };
    use crate::native_core::scope_index::RuleCandidateOutput;
    use crate::native_core::scope_index::RuleCandidateTextRules;

    fn text_rules() -> RuleCandidateTextRules {
        RuleCandidateTextRules {
            custom_placeholder_rules: Vec::new(),
            structured_placeholder_rules: Vec::new(),
            strip_wrapping_punctuation_pairs: vec![("「".to_string(), "」".to_string())],
            source_text_required_pattern: r"[\p{Han}\p{Hiragana}\p{Katakana}]".to_string(),
            source_text_exclusion_profile: "none".to_string(),
        }
    }

    fn source_file(file_name: &str, source: &str, active: bool) -> PluginSourceFileInput {
        PluginSourceFileInput {
            file_name: file_name.to_string(),
            source: source.to_string(),
            active,
        }
    }

    #[test]
    fn scan_plugin_source_candidates_decodes_escapes_and_reports_active_syntax_summary() {
        let files = vec![
            source_file(
                "EnabledSource.js",
                r"
const Messages = {
  title: '\u52C7\u8005',
  wrapped: '「包まれた文」',
  control: '頑張って\\nn[0]くん',
  resource: 'audio/se/cursor.ogg'
};
Window_Base.prototype.drawText('短い', 0, 0, 320);
",
                true,
            ),
            source_file(
                "DisabledSource.js",
                "const Disabled = { title: '未使用の文' };",
                false,
            ),
            source_file(
                "BrokenSource.js",
                "const Broken = { title: '壊れた本文',",
                true,
            ),
        ];

        let scan = scan_plugin_source_rule_candidates(&files, text_rules()).expect("扫描应成功");

        let texts = scan
            .candidates
            .iter()
            .map(|candidate| candidate.original_text.as_str())
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(
            texts,
            std::collections::BTreeSet::from([
                "勇者",
                "「包まれた文」",
                r"頑張って\nn[0]くん",
                "短い",
                "未使用の文",
            ])
        );
        assert_eq!(scan.scanned_file_count, 2);
        assert_eq!(scan.ignored_file_count, 1);
        assert_eq!(scan.syntax_error_file_count, 1);
        assert_eq!(scan.syntax_errors[0]["file"], "BrokenSource.js");

        let short = scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "短い")
            .expect("短い 候选应存在");
        assert_eq!(short.source_file, "EnabledSource.js");
        assert_eq!(short.active, Some(true));
        assert_eq!(short.confidence.as_deref(), Some("strong"));
        assert_eq!(short.raw_text.as_deref(), Some("短い"));
        assert_eq!(short.quote.as_deref(), Some("'"));
        assert_eq!(short.line, Some(8));
        assert!(short.selector.as_deref().is_some_and(|selector| {
            short.location_path == format!("js/plugins/EnabledSource.js/{selector}")
        }));

        let disabled = scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "未使用の文")
            .expect("禁用插件候选应保留以便报告 ignored 状态");
        assert_eq!(disabled.active, Some(false));

        let control = scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text.contains("nn[0]"))
            .expect("控制符字面量候选应存在");
        assert!(!control.original_text.contains('\n'));
        assert!(control.original_text.contains(r"\nn[0]"));
    }

    #[test]
    fn collect_plugin_source_managed_texts_requires_review_for_each_active_candidate() {
        let files = vec![source_file(
            "HardcodedText.js",
            "const Messages = { first: '一番目', second: '二番目' };",
            true,
        )];
        let scan = scan_plugin_source_rule_candidates(&files, text_rules()).expect("扫描应成功");
        let first_selector = scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "一番目")
            .and_then(|candidate| candidate.selector.clone())
            .expect("一番目 selector 应存在");
        let second_selector = scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "二番目")
            .and_then(|candidate| candidate.selector.clone())
            .expect("二番目 selector 应存在");

        let incomplete = collect_plugin_source_managed_texts(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "HardcodedText.js".to_string(),
                selectors: vec![first_selector.clone()],
                excluded_selectors: Vec::new(),
            }],
            text_rules(),
        );
        assert!(matches!(
            incomplete,
            Err(PluginSourceManagedTextError::ReviewIncomplete {
                unreviewed_count: 1
            })
        ));

        let managed_result = collect_plugin_source_managed_texts(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "HardcodedText.js".to_string(),
                selectors: vec![first_selector.clone()],
                excluded_selectors: vec![second_selector],
            }],
            text_rules(),
        );
        let managed = match managed_result {
            Ok(managed) => managed,
            Err(_) => panic!("完整审查后应返回 managed 文本"),
        };
        assert_eq!(managed.len(), 1);
        assert_eq!(managed[0].file_name, "HardcodedText.js");
        assert_eq!(managed[0].selector, first_selector);
        assert_eq!(managed[0].text, "一番目");
    }

    fn scan_plugin_source_fixture_with_rules() -> super::PluginSourceRuleCandidateScan {
        let files = vec![source_file(
            "ReviewedSource.js",
            "const Messages = { first: '一番目', second: '二番目' };",
            true,
        )];
        let initial_scan =
            scan_plugin_source_rule_candidates(&files, text_rules()).expect("扫描应成功");
        let first_selector = initial_scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "一番目")
            .and_then(|candidate| candidate.selector.clone())
            .expect("一番目 selector 应存在");
        let second_selector = initial_scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "二番目")
            .and_then(|candidate| candidate.selector.clone())
            .expect("二番目 selector 应存在");

        super::scan_plugin_source_rule_candidates_with_rules(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "ReviewedSource.js".to_string(),
                selectors: vec![first_selector],
                excluded_selectors: vec![second_selector],
            }],
            text_rules(),
            0,
        )
        .expect("带规则扫描应成功")
    }

    fn scan_plugin_source_fixture_with_filtered_text() -> super::PluginSourceRuleCandidateScan {
        let files = vec![source_file(
            "FilteredSource.js",
            "const Messages = { protocol: 'this.value()' };",
            true,
        )];
        let mut initial_rules = text_rules();
        initial_rules.source_text_required_pattern = r"[\s\S]".to_string();
        let initial_scan =
            scan_plugin_source_rule_candidates(&files, initial_rules).expect("扫描应成功");
        let raw_selector = initial_scan
            .candidates
            .iter()
            .find(|candidate| candidate.original_text == "this.value()")
            .and_then(|candidate| candidate.selector.clone())
            .expect("this.value() selector 应存在");
        let mut rules = text_rules();
        rules.source_text_required_pattern = r"[\s\S]".to_string();
        rules.source_text_exclusion_profile = "english_protocol_noise".to_string();
        super::scan_plugin_source_rule_candidates_with_rules(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "FilteredSource.js".to_string(),
                selectors: vec![raw_selector],
                excluded_selectors: Vec::new(),
            }],
            rules,
            0,
        )
        .expect("过滤文本扫描应成功")
    }

    #[test]
    fn plugin_source_scan_outputs_selector_facts_and_review_summary() {
        let result = scan_plugin_source_fixture_with_rules();

        assert_eq!(result.review_summary.total_selector_count, 2);
        assert_eq!(result.review_summary.excluded_selector_count, 1);
        assert_eq!(result.selector_facts[0].stale_reason, None);
        assert!(!result.risk_summary.high_risk);
        assert!(!result.scope_hash.is_empty());
    }

    #[test]
    fn plugin_source_scan_reports_filtered_selector_reason() {
        let result = scan_plugin_source_fixture_with_filtered_text();

        assert_eq!(
            result.selector_facts[0]
                .stale_reason
                .as_ref()
                .map(|reason| reason.code.as_str()),
            Some("selector_filtered")
        );
    }

    #[test]
    fn collect_plugin_source_managed_texts_rejects_stale_file_selector_or_inactive_file() {
        let files = vec![
            source_file("Active.js", "const Messages = { title: '有効本文' };", true),
            source_file(
                "Inactive.js",
                "const Messages = { title: '無効本文' };",
                false,
            ),
        ];

        let missing_file = collect_plugin_source_managed_texts(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "Missing.js".to_string(),
                selectors: vec!["ast:string:0:1:missing".to_string()],
                excluded_selectors: Vec::new(),
            }],
            text_rules(),
        );
        assert!(
            matches!(missing_file, Err(PluginSourceManagedTextError::Stale(message)) if message.contains("文件不存在"))
        );

        let inactive_file = collect_plugin_source_managed_texts(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "Inactive.js".to_string(),
                selectors: Vec::new(),
                excluded_selectors: Vec::new(),
            }],
            text_rules(),
        );
        assert!(
            matches!(inactive_file, Err(PluginSourceManagedTextError::Stale(message)) if message.contains("未在 plugins.js 中启用"))
        );

        let stale_selector = collect_plugin_source_managed_texts(
            &files,
            &[PluginSourceTextRuleInput {
                file_name: "Active.js".to_string(),
                selectors: vec!["ast:string:0:1:missing".to_string()],
                excluded_selectors: Vec::new(),
            }],
            text_rules(),
        );
        assert!(
            matches!(stale_selector, Err(PluginSourceManagedTextError::Stale(message)) if message.contains("selector 已无法命中"))
        );
    }

    #[test]
    fn plugin_source_managed_text_rejects_candidate_missing_raw_span_fields() {
        let mut candidate = RuleCandidateOutput {
            domain: "plugin_source".to_string(),
            location_path: "js/plugins/Test.js/ast:string:1:7:abcdef".to_string(),
            rule_key: "ast:string:1:7:abcdef".to_string(),
            original_text: "本文".to_string(),
            source_file: "Test.js".to_string(),
            file: Some("Test.js".to_string()),
            json_path: None,
            source_text: None,
            field_name: None,
            sibling_field_names: None,
            parent_object_keys: None,
            selector: Some("ast:string:1:7:abcdef".to_string()),
            text: Some("本文".to_string()),
            raw_text: None,
            quote: Some("'".to_string()),
            line: Some(1),
            start_index: Some(1),
            end_index: Some(7),
            content_start_index: Some(2),
            content_end_index: Some(6),
            context: None,
            api: None,
            key: None,
            ast_context: None,
            active: Some(true),
            confidence: None,
            structural_flags: None,
            file_hash: Some("hash".to_string()),
        };

        let error = plugin_source_managed_text_from_candidate(
            "Test.js",
            "ast:string:1:7:abcdef",
            &candidate,
        )
        .expect_err("插件源码候选缺少 raw_text 时必须显式失败");

        assert!(
            matches!(error, PluginSourceManagedTextError::InvalidCandidate(message) if message.contains("raw_text"))
        );

        candidate.raw_text = Some("本文".to_string());
        candidate.start_index = None;
        let error = plugin_source_managed_text_from_candidate(
            "Test.js",
            "ast:string:1:7:abcdef",
            &candidate,
        )
        .expect_err("插件源码候选缺少 span 时必须显式失败");

        assert!(
            matches!(error, PluginSourceManagedTextError::InvalidCandidate(message) if message.contains("start_index"))
        );
    }
}
