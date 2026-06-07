//! JavaScript AST 字符串节点扫描。
//!
//! 本模块解析源码，返回稳定范围，并输出运行审计需要的字符串分类事实。

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use tree_sitter::{Node, Parser};

use super::controls::{
    ControlCodeHint, collect_control_code_hints, collect_unprotected_control_sequences,
};
use super::models::{CompiledRules, NativeTextRules};
use super::pool::run_with_optional_pool;
use super::rules::compile_rules;
use rayon::prelude::*;

#[derive(Debug, Deserialize)]
struct JavaScriptAstPayload {
    source: String,
}

#[derive(Debug, Deserialize)]
struct JavaScriptAstBatchPayload {
    files: Vec<JavaScriptAstBatchInput>,
}

#[derive(Clone, Debug, Deserialize)]
struct JavaScriptAstBatchInput {
    file_name: String,
    source: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeLiteralIssueFactsPayload {
    literals: Vec<RuntimeLiteralIssueFactsInput>,
    text_rules: NativeTextRules,
}

#[derive(Debug, Deserialize)]
struct RuntimeLiteralIssueFactsInput {
    id: String,
    raw_text: String,
    text: String,
    literal_kind: String,
    audit_default_severity: String,
}

#[derive(Debug, Serialize)]
struct RuntimeLiteralIssueFactsResult {
    facts: Vec<RuntimeLiteralIssueFactOutput>,
}

#[derive(Debug, Serialize)]
struct RuntimeLiteralIssueFactOutput {
    id: String,
    literal_kind: String,
    audit_default_severity: String,
    issue_codes: Vec<String>,
    placeholder_fragments: Vec<String>,
    control_code_hints: Vec<ControlCodeHint>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct JavaScriptStringSpan {
    pub(crate) kind: String,
    pub(crate) quote: String,
    pub(crate) start_index: usize,
    pub(crate) end_index: usize,
    pub(crate) content_start_index: usize,
    pub(crate) content_end_index: usize,
    pub(crate) content_start_byte_index: usize,
    #[serde(skip_serializing)]
    pub(crate) content_end_byte_index: usize,
    pub(crate) ast_context: JavaScriptStringAstContext,
    pub(crate) literal_kind: String,
    pub(crate) audit_default_severity: String,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct JavaScriptStringAstContext {
    pub(crate) node_kind: String,
    pub(crate) property_key: String,
    pub(crate) property_path: Vec<String>,
    pub(crate) call_name: String,
    pub(crate) call_argument_index: Option<usize>,
    pub(crate) return_function_name: String,
    pub(crate) assignment_name: String,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct JavaScriptAstOutput {
    pub(crate) has_error: bool,
    pub(crate) spans: Vec<JavaScriptStringSpan>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct JavaScriptAstFileOutput {
    pub(crate) file_name: String,
    pub(crate) has_error: bool,
    pub(crate) spans: Vec<JavaScriptStringSpan>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct JavaScriptAstBatchOutput {
    pub(crate) files: Vec<JavaScriptAstFileOutput>,
}

pub(crate) fn parse_javascript_string_spans_impl(payload_json: &str) -> Result<String, String> {
    let payload: JavaScriptAstPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("JS AST 输入不是有效 JSON: {error}"))?;
    let output = parse_javascript_string_spans(&payload.source)?;
    serde_json::to_string(&output).map_err(|error| format!("JS AST 输出 JSON 失败: {error}"))
}

pub(crate) fn parse_javascript_string_spans_batch_impl(
    payload_json: &str,
) -> Result<String, String> {
    let payload: JavaScriptAstBatchPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("批量 JS AST 输入不是有效 JSON: {error}"))?;
    let files = run_with_optional_pool(|| {
        payload
            .files
            .par_iter()
            .map(parse_javascript_file_spans)
            .collect::<Result<Vec<_>, String>>()
    })??;
    let output = JavaScriptAstBatchOutput { files };
    serde_json::to_string(&output).map_err(|error| format!("批量 JS AST 输出 JSON 失败: {error}"))
}

pub(crate) fn collect_runtime_literal_issue_facts_impl(
    payload_json: &str,
) -> Result<String, String> {
    let payload: RuntimeLiteralIssueFactsPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("运行源码字符串风险事实输入不是有效 JSON: {error}"))?;
    let rules = compile_rules(payload.text_rules)?;
    let mut facts = Vec::with_capacity(payload.literals.len());
    for literal in payload.literals {
        facts.push(collect_runtime_literal_issue_fact(literal, &rules)?);
    }
    let output = RuntimeLiteralIssueFactsResult { facts };
    serde_json::to_string(&output)
        .map_err(|error| format!("运行源码字符串风险事实输出 JSON 失败: {error}"))
}

fn collect_runtime_literal_issue_fact(
    literal: RuntimeLiteralIssueFactsInput,
    rules: &CompiledRules,
) -> Result<RuntimeLiteralIssueFactOutput, String> {
    let mut fragments = BTreeSet::new();
    fragments.extend(collect_linebreak_control_fragments(
        &literal.raw_text,
        &literal.text,
    ));
    let lines = vec![literal.text.clone()];
    for (fragment, _count) in collect_unprotected_control_sequences(&lines, rules)? {
        fragments.insert(fragment);
    }
    let control_code_hints = collect_control_code_hints(&lines, rules);
    let placeholder_fragments = fragments.into_iter().collect::<Vec<_>>();
    let issue_codes = if placeholder_fragments.is_empty() {
        Vec::new()
    } else {
        vec!["active_runtime_placeholder_risk".to_string()]
    };
    Ok(RuntimeLiteralIssueFactOutput {
        id: literal.id,
        literal_kind: literal.literal_kind,
        audit_default_severity: literal.audit_default_severity,
        issue_codes,
        placeholder_fragments,
        control_code_hints,
    })
}

fn collect_linebreak_control_fragments(raw_text: &str, text: &str) -> BTreeSet<String> {
    let mut fragments = BTreeSet::new();
    let mut search_start = 0usize;
    while let Some(relative_index) = raw_text[search_start..].find(r"\n") {
        let marker_index = search_start + relative_index;
        if marker_index == 0 || !raw_text[..marker_index].ends_with('\\') {
            let fragment_start = marker_index + 2;
            if let Some(fragment) = read_visible_control_fragment(raw_text, fragment_start) {
                fragments.insert(fragment);
            }
        }
        search_start = marker_index + 2;
    }
    for (byte_index, char_value) in text.char_indices() {
        if char_value != '\n' && char_value != '\r' {
            continue;
        }
        let fragment_start = byte_index + char_value.len_utf8();
        if let Some(fragment) = read_visible_control_fragment(text, fragment_start) {
            fragments.insert(fragment);
        }
    }
    fragments
}

fn read_visible_control_fragment(text: &str, byte_start: usize) -> Option<String> {
    let tail = text.get(byte_start..)?;
    let mut chars = tail.char_indices().peekable();
    let mut has_letter = false;
    while let Some((_relative_index, char_value)) = chars.peek().copied() {
        if !char_value.is_ascii_alphabetic() {
            break;
        }
        has_letter = true;
        chars.next();
    }
    if !has_letter {
        return None;
    }
    while let Some((_relative_index, char_value)) = chars.peek().copied() {
        if !char_value.is_ascii_digit() {
            break;
        }
        chars.next();
    }
    let (_relative_index, char_value) = chars.next()?;
    if char_value != '[' {
        return None;
    }
    let mut bracket_content_len = 0usize;
    for (relative_index, char_value) in chars {
        if char_value == '\r' || char_value == '\n' {
            return None;
        }
        if char_value == ']' {
            let end = byte_start + relative_index + char_value.len_utf8();
            return text.get(byte_start..end).map(str::to_string);
        }
        bracket_content_len += 1;
        if bracket_content_len > 64 {
            return None;
        }
    }
    None
}

fn parse_javascript_file_spans(
    input: &JavaScriptAstBatchInput,
) -> Result<JavaScriptAstFileOutput, String> {
    let output = parse_javascript_string_spans(&input.source)
        .map_err(|error| format!("{} JS AST 解析失败: {error}", input.file_name))?;
    Ok(JavaScriptAstFileOutput {
        file_name: input.file_name.clone(),
        has_error: output.has_error,
        spans: output.spans,
    })
}

pub(crate) fn parse_javascript_string_spans(source: &str) -> Result<JavaScriptAstOutput, String> {
    let mut parser = Parser::new();
    let language = tree_sitter_javascript::LANGUAGE;
    parser
        .set_language(&language.into())
        .map_err(|error| format!("JS AST 语言初始化失败: {error}"))?;
    let tree = parser
        .parse(source, None)
        .ok_or_else(|| "JS AST 解析失败".to_string())?;
    let root = tree.root_node();
    let mut spans: Vec<JavaScriptStringSpan> = Vec::new();
    let char_indices = CharIndexLookup::new(source);
    collect_string_nodes(root, source, &char_indices, &mut spans);
    Ok(JavaScriptAstOutput {
        has_error: root.has_error(),
        spans,
    })
}

fn collect_string_nodes(
    node: Node<'_>,
    source: &str,
    char_indices: &CharIndexLookup,
    spans: &mut Vec<JavaScriptStringSpan>,
) {
    if node.kind() == "string"
        && let Some(span) = build_string_span(node, source, char_indices)
    {
        spans.push(span);
    }
    if node.kind() == "string_fragment"
        && node
            .parent()
            .is_some_and(|parent| parent.kind() == "template_string")
        && let Some(span) = build_template_fragment_span(node, source, char_indices)
    {
        spans.push(span);
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_string_nodes(child, source, char_indices, spans);
    }
}

fn build_string_span(
    node: Node<'_>,
    source: &str,
    char_indices: &CharIndexLookup,
) -> Option<JavaScriptStringSpan> {
    let start_byte = node.start_byte();
    let end_byte = node.end_byte();
    let raw = source.get(start_byte..end_byte)?;
    let quote = raw.chars().next()?;
    if quote != '\'' && quote != '"' {
        return None;
    }
    let start_index = char_indices.char_index(start_byte)?;
    let end_index = char_indices.char_index(end_byte)?;
    if end_index <= start_index + 1 {
        return None;
    }
    let content_start_byte = start_byte + quote.len_utf8();
    let content_end_byte = end_byte.checked_sub(quote.len_utf8())?;
    let raw_text = source.get(content_start_byte..content_end_byte)?;
    let ast_context = build_ast_context(node, source);
    let (literal_kind, audit_default_severity) =
        classify_javascript_literal(raw_text, &ast_context);
    Some(JavaScriptStringSpan {
        kind: node.kind().to_string(),
        quote: quote.to_string(),
        start_index,
        end_index,
        content_start_index: start_index + 1,
        content_end_index: end_index - 1,
        content_start_byte_index: content_start_byte,
        content_end_byte_index: content_end_byte,
        ast_context,
        literal_kind,
        audit_default_severity,
    })
}

fn build_template_fragment_span(
    node: Node<'_>,
    source: &str,
    char_indices: &CharIndexLookup,
) -> Option<JavaScriptStringSpan> {
    let start_byte = node.start_byte();
    let end_byte = node.end_byte();
    let start_index = char_indices.char_index(start_byte)?;
    let end_index = char_indices.char_index(end_byte)?;
    if end_index <= start_index {
        return None;
    }
    let raw_text = source.get(start_byte..end_byte)?;
    let ast_context = build_ast_context(node, source);
    let (literal_kind, audit_default_severity) =
        classify_javascript_literal(raw_text, &ast_context);
    Some(JavaScriptStringSpan {
        kind: "template_fragment".to_string(),
        quote: "`".to_string(),
        start_index,
        end_index,
        content_start_index: start_index,
        content_end_index: end_index,
        content_start_byte_index: start_byte,
        content_end_byte_index: end_byte,
        ast_context,
        literal_kind,
        audit_default_severity,
    })
}

fn classify_javascript_literal(
    raw_text: &str,
    context: &JavaScriptStringAstContext,
) -> (String, String) {
    if is_eval_call_context(&context.call_name) {
        return ("eval_code".to_string(), "warning".to_string());
    }
    if looks_like_packer_code(raw_text) {
        return ("packer_code".to_string(), "warning".to_string());
    }
    if looks_like_regex_pattern(raw_text) {
        return ("regex_pattern".to_string(), "warning".to_string());
    }
    if looks_like_user_visible_context(context) {
        return ("user_visible_candidate".to_string(), "blocking".to_string());
    }
    ("unknown".to_string(), "warning".to_string())
}

fn is_eval_call_context(call_name: &str) -> bool {
    call_name == "eval" || call_name.ends_with(".eval")
}

fn looks_like_packer_code(raw_text: &str) -> bool {
    let compact_text: String = raw_text
        .chars()
        .filter(|char| !char.is_whitespace())
        .collect::<String>()
        .to_ascii_lowercase();
    compact_text.contains("function(p,a,c,k,e")
        || compact_text.contains("function(p,h,e")
        || (compact_text.contains("eval(function(") && compact_text.contains(".split('|')"))
}

fn looks_like_regex_pattern(raw_text: &str) -> bool {
    let compact_text = raw_text.trim();
    if compact_text.is_empty() {
        return false;
    }
    let escaped_regex_tokens = [
        "\\\\w", "\\\\W", "\\\\d", "\\\\D", "\\\\s", "\\\\S", "\\\\b", "\\\\B", "\\\\p{", "\\\\P{",
    ];
    if escaped_regex_tokens
        .iter()
        .any(|token| compact_text.contains(token))
    {
        return true;
    }
    let regex_groups = ["(?:", "(?=", "(?!", "(?<=", "(?<!", "(?<"];
    if regex_groups
        .iter()
        .any(|token| compact_text.contains(token))
    {
        return true;
    }
    let has_character_class = compact_text.contains('[') && compact_text.contains(']');
    let has_regex_quantifier = compact_text.contains('*')
        || compact_text.contains('+')
        || compact_text.contains('?')
        || compact_text.contains('{');
    has_character_class && has_regex_quantifier
}

fn looks_like_user_visible_context(context: &JavaScriptStringAstContext) -> bool {
    const STRONG_TEXT_KEYS: &[&str] = &[
        "body",
        "caption",
        "description",
        "help",
        "helpLines",
        "label",
        "longDescription",
        "message",
        "name",
        "nickName",
        "param1",
        "param2",
        "shortDescription",
        "stanceDescription",
        "text",
        "title",
    ];
    const STRONG_CALL_SUFFIXES: &[&str] = &[
        "addCommand",
        "addText",
        "drawText",
        "drawTextEx",
        "setText",
        "$gameMessage.add",
    ];
    if STRONG_TEXT_KEYS.contains(&context.property_key.as_str()) {
        return true;
    }
    STRONG_CALL_SUFFIXES
        .iter()
        .any(|suffix| context.call_name == *suffix || context.call_name.ends_with(suffix))
}

fn build_ast_context(node: Node<'_>, source: &str) -> JavaScriptStringAstContext {
    let (call_name, call_argument_index) =
        collect_call_context(node, source).unwrap_or_else(|| (String::new(), None));
    let property_path = collect_property_path(node, source);
    let property_key = property_path.last().cloned().unwrap_or_default();
    JavaScriptStringAstContext {
        node_kind: node.kind().to_string(),
        property_key,
        property_path,
        call_name,
        call_argument_index,
        return_function_name: collect_return_function_name(node, source).unwrap_or_default(),
        assignment_name: collect_assignment_name(node, source).unwrap_or_default(),
    }
}

fn collect_property_path(node: Node<'_>, source: &str) -> Vec<String> {
    let mut keys: Vec<String> = Vec::new();
    let mut current = node.parent();
    while let Some(parent) = current {
        if parent.kind() == "pair"
            && parent
                .child_by_field_name("value")
                .is_some_and(|value| node_contains(value, node))
            && let Some(key_node) = parent.child_by_field_name("key")
            && let Some(key) = property_key_text(key_node, source)
        {
            keys.push(key);
        }
        current = parent.parent();
    }
    keys.reverse();
    keys
}

fn collect_call_context(node: Node<'_>, source: &str) -> Option<(String, Option<usize>)> {
    let mut current = node.parent();
    while let Some(parent) = current {
        if parent.kind() == "arguments"
            && let Some(call_expression) = parent.parent()
            && call_expression.kind() == "call_expression"
            && let Some(function_node) = call_expression.child_by_field_name("function")
        {
            let call_name = node_text(function_node, source)?.trim().to_string();
            return Some((call_name, argument_index(parent, node)));
        }
        current = parent.parent();
    }
    None
}

fn argument_index(arguments_node: Node<'_>, target_node: Node<'_>) -> Option<usize> {
    let mut cursor = arguments_node.walk();
    for (index, child) in arguments_node.named_children(&mut cursor).enumerate() {
        if node_contains(child, target_node) {
            return Some(index);
        }
    }
    None
}

fn collect_return_function_name(node: Node<'_>, source: &str) -> Option<String> {
    let mut current = node.parent();
    while let Some(parent) = current {
        if parent.kind() == "return_statement" && node_contains(parent, node) {
            return enclosing_function_name(parent, source);
        }
        current = parent.parent();
    }
    None
}

fn enclosing_function_name(node: Node<'_>, source: &str) -> Option<String> {
    let mut current = node.parent();
    while let Some(parent) = current {
        if is_function_like(parent.kind()) {
            return function_name(parent, source);
        }
        current = parent.parent();
    }
    None
}

fn is_function_like(kind: &str) -> bool {
    matches!(
        kind,
        "function_declaration"
            | "function_expression"
            | "generator_function_declaration"
            | "generator_function"
            | "arrow_function"
            | "method_definition"
    )
}

fn function_name(node: Node<'_>, source: &str) -> Option<String> {
    if let Some(name_node) = node.child_by_field_name("name")
        && let Some(name) = node_text(name_node, source)
    {
        return Some(name.trim().to_string());
    }
    if let Some(parent) = node.parent() {
        if parent.kind() == "pair"
            && parent
                .child_by_field_name("value")
                .is_some_and(|value| node_contains(value, node))
            && let Some(key_node) = parent.child_by_field_name("key")
        {
            return property_key_text(key_node, source);
        }
        if parent.kind() == "variable_declarator"
            && parent
                .child_by_field_name("value")
                .is_some_and(|value| node_contains(value, node))
            && let Some(name_node) = parent.child_by_field_name("name")
        {
            return node_text(name_node, source).map(|text| text.trim().to_string());
        }
        if parent.kind() == "assignment_expression"
            && parent
                .child_by_field_name("right")
                .is_some_and(|right| node_contains(right, node))
            && let Some(left_node) = parent.child_by_field_name("left")
        {
            return node_text(left_node, source).map(|text| text.trim().to_string());
        }
    }
    None
}

fn collect_assignment_name(node: Node<'_>, source: &str) -> Option<String> {
    let mut current = node.parent();
    while let Some(parent) = current {
        if parent.kind() == "assignment_expression"
            && parent
                .child_by_field_name("right")
                .is_some_and(|right| node_contains(right, node))
            && let Some(left_node) = parent.child_by_field_name("left")
        {
            return node_text(left_node, source).map(|text| text.trim().to_string());
        }
        if parent.kind() == "variable_declarator"
            && parent
                .child_by_field_name("value")
                .is_some_and(|value| node_contains(value, node))
            && let Some(name_node) = parent.child_by_field_name("name")
        {
            return node_text(name_node, source).map(|text| text.trim().to_string());
        }
        current = parent.parent();
    }
    None
}

fn property_key_text(node: Node<'_>, source: &str) -> Option<String> {
    let raw_text = node_text(node, source)?.trim().to_string();
    if raw_text.len() >= 2
        && ((raw_text.starts_with('\'') && raw_text.ends_with('\''))
            || (raw_text.starts_with('"') && raw_text.ends_with('"')))
    {
        return Some(raw_text[1..raw_text.len() - 1].to_string());
    }
    Some(raw_text)
}

fn node_contains(parent: Node<'_>, child: Node<'_>) -> bool {
    parent.start_byte() <= child.start_byte() && parent.end_byte() >= child.end_byte()
}

fn node_text<'a>(node: Node<'_>, source: &'a str) -> Option<&'a str> {
    source.get(node.start_byte()..node.end_byte())
}

struct CharIndexLookup {
    byte_offsets: Vec<usize>,
}

impl CharIndexLookup {
    fn new(source: &str) -> Self {
        let mut byte_offsets: Vec<usize> =
            source.char_indices().map(|(index, _char)| index).collect();
        byte_offsets.push(source.len());
        Self { byte_offsets }
    }

    fn char_index(&self, byte_index: usize) -> Option<usize> {
        self.byte_offsets.binary_search(&byte_index).ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    #[test]
    fn parses_string_nodes_and_skips_comments() {
        let payload = json!({
            "source": "// drawText('コメント')\nconst a = '日文'; const b = \"English\";"
        });
        let output =
            parse_javascript_string_spans_impl(&payload.to_string()).expect("JS AST 扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        assert_eq!(value["has_error"], json!(false));
        assert_eq!(value["spans"].as_array().map(Vec::len), Some(2));
        assert_eq!(value["spans"][0]["quote"], json!("'"));
    }

    #[test]
    fn returns_ast_context_for_arrays_returns_and_calls() {
        let payload = json!({
            "source": "const x = { param2: ['プフクスッ'] };\nfunction termSecondPerson() { return 'キミ'; }\nWindow_Base.prototype.drawText('短い', 0, 0);"
        });
        let output =
            parse_javascript_string_spans_impl(&payload.to_string()).expect("JS AST 扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        let spans = value["spans"].as_array().expect("spans 应为数组");
        assert_eq!(spans[0]["ast_context"]["property_key"], json!("param2"));
        assert_eq!(spans[0]["ast_context"]["property_path"], json!(["param2"]));
        assert_eq!(
            spans[1]["ast_context"]["return_function_name"],
            json!("termSecondPerson")
        );
        assert_eq!(
            spans[2]["ast_context"]["call_name"],
            json!("Window_Base.prototype.drawText")
        );
        assert_eq!(spans[2]["ast_context"]["call_argument_index"], json!(0));
    }

    #[test]
    fn parses_template_static_fragments() {
        let payload = json!({
            "source": "const text = `名前: ${actor.name} さん`;"
        });
        let output =
            parse_javascript_string_spans_impl(&payload.to_string()).expect("JS AST 扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        assert_eq!(value["has_error"], json!(false));
        assert_eq!(value["spans"].as_array().map(Vec::len), Some(2));
        assert_eq!(value["spans"][0]["quote"], json!("`"));
    }

    #[test]
    fn classifies_runtime_literal_audit_facts() {
        let payload = json!({
            "source": concat!(
                "function matcher() { return '\\\\w+'; }\n",
                "eval('packed source');\n",
                "const config = { title: '未審査テキスト' };\n",
                "const misc = '未分類';\n"
            )
        });
        let output =
            parse_javascript_string_spans_impl(&payload.to_string()).expect("JS AST 扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        let spans = value["spans"].as_array().expect("spans 应为数组");

        assert_eq!(spans[0]["literal_kind"], json!("regex_pattern"));
        assert_eq!(spans[0]["audit_default_severity"], json!("warning"));
        assert_eq!(spans[1]["literal_kind"], json!("eval_code"));
        assert_eq!(spans[1]["audit_default_severity"], json!("warning"));
        assert_eq!(spans[2]["literal_kind"], json!("user_visible_candidate"));
        assert_eq!(spans[2]["audit_default_severity"], json!("blocking"));
        assert_eq!(spans[3]["literal_kind"], json!("unknown"));
        assert_eq!(spans[3]["audit_default_severity"], json!("warning"));
    }

    #[test]
    fn runtime_literal_issue_facts_report_control_fragments_and_hints() {
        let payload = json!({
            "literals": [
                {
                    "id": "plain",
                    "raw_text": "\\\\ii[1]",
                    "text": "\\ii[1]",
                    "literal_kind": "unknown",
                    "audit_default_severity": "warning"
                },
                {
                    "id": "linebreak",
                    "raw_text": "prefix\\nN[1]",
                    "text": "prefix\nN[1]",
                    "literal_kind": "unknown",
                    "audit_default_severity": "warning"
                },
                {
                    "id": "hint",
                    "raw_text": "\\\\fb21st",
                    "text": "\\fb21st",
                    "literal_kind": "unknown",
                    "audit_default_severity": "warning"
                }
            ],
            "text_rules": minimal_text_rules(),
        });
        let output = collect_runtime_literal_issue_facts_impl(&payload.to_string())
            .expect("运行字符串风险事实应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        let facts = value["facts"].as_array().expect("facts 应为数组");

        assert_eq!(facts[0]["id"], json!("plain"));
        assert_eq!(
            facts[0]["issue_codes"],
            json!(["active_runtime_placeholder_risk"])
        );
        assert_eq!(facts[0]["placeholder_fragments"], json!(["\\ii[1]"]));
        assert_eq!(facts[1]["placeholder_fragments"], json!(["N[1]"]));
        assert_eq!(facts[2]["placeholder_fragments"], json!(["\\fb21"]));
        assert_eq!(
            facts[2]["control_code_hints"][0]["original"],
            json!("\\fb21st")
        );
        assert_eq!(
            facts[2]["control_code_hints"][0]["hint_kind"],
            json!("possible_control_split")
        );
    }

    #[test]
    fn runtime_literal_issue_facts_preserve_ast_literal_classification() {
        let payload = json!({
            "literals": [
                {
                    "id": "regex",
                    "raw_text": "\\\\w+",
                    "text": "\\w+",
                    "literal_kind": "regex_pattern",
                    "audit_default_severity": "warning"
                },
                {
                    "id": "visible",
                    "raw_text": "未審査テキスト",
                    "text": "未審査テキスト",
                    "literal_kind": "user_visible_candidate",
                    "audit_default_severity": "blocking"
                }
            ],
            "text_rules": minimal_text_rules(),
        });
        let output = collect_runtime_literal_issue_facts_impl(&payload.to_string())
            .expect("运行字符串风险事实应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        let facts = value["facts"].as_array().expect("facts 应为数组");

        assert_eq!(facts[0]["id"], json!("regex"));
        assert_eq!(facts[0]["literal_kind"], json!("regex_pattern"));
        assert_eq!(facts[0]["audit_default_severity"], json!("warning"));
        assert_eq!(facts[1]["id"], json!("visible"));
        assert_eq!(facts[1]["literal_kind"], json!("user_visible_candidate"));
        assert_eq!(facts[1]["audit_default_severity"], json!("blocking"));
    }

    #[test]
    fn runtime_literal_issue_facts_reject_missing_literal_classification() {
        let payload = json!({
            "literals": [
                {
                    "id": "missing",
                    "raw_text": "\\\\w+",
                    "text": "\\w+"
                }
            ],
            "text_rules": minimal_text_rules(),
        });

        let error = collect_runtime_literal_issue_facts_impl(&payload.to_string())
            .expect_err("运行字符串风险事实输入缺少分类字段时必须显式失败");

        assert!(error.contains("literal_kind"));
    }

    #[test]
    fn parses_string_nodes_for_batch_files() {
        let payload = json!({
            "files": [
                {"file_name": "A.js", "source": "const a = '日文';"},
                {"file_name": "B.js", "source": "Window_Base.prototype.drawText('短い', 0, 0);"}
            ]
        });
        let output = parse_javascript_string_spans_batch_impl(&payload.to_string())
            .expect("批量 JS AST 扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        assert_eq!(value["files"].as_array().map(Vec::len), Some(2));
        assert_eq!(value["files"][0]["file_name"], json!("A.js"));
        assert_eq!(value["files"][0]["spans"].as_array().map(Vec::len), Some(1));
        assert_eq!(value["files"][1]["file_name"], json!("B.js"));
        assert_eq!(
            value["files"][1]["spans"][0]["ast_context"]["call_name"],
            json!("Window_Base.prototype.drawText")
        );
    }

    fn minimal_text_rules() -> Value {
        json!({
            "custom_placeholder_rules": [],
            "structured_placeholder_rules": [],
            "source_residual_allowed_chars": [],
            "source_residual_allowed_tail_chars": [],
            "source_residual_segment_pattern": r"[\p{Hiragana}\p{Katakana}\p{Han}]+",
            "source_residual_label": "日文",
            "allowed_source_residual_terms": [],
            "source_residual_terms_ignore_case": true,
            "source_residual_detection_profile": "japanese_strict",
            "english_source_copy_min_words": 4,
            "english_source_copy_min_letters": 12,
            "line_width_count_pattern": r"\S",
            "residual_escape_sequence_pattern": r"\\[nrt]",
            "long_text_line_width_limit": 26
        })
    }

    #[test]
    fn batch_ast_accepts_thread_pool_config_on_hot_path() {
        let payload = json!({
            "files": [
                {"file_name": "A.js", "source": "const a = '日文';"},
                {"file_name": "B.js", "source": "const b = '短い';"}
            ]
        });

        let result =
            crate::native_core::pool::with_thread_count_override_for_test(Some("1"), || {
                parse_javascript_string_spans_batch_impl(&payload.to_string())
            });
        let output = result.expect("批量 JS AST 热路径应接受 runtime.rust_threads 配置");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(value["files"].as_array().map(Vec::len), Some(2));
    }

    #[test]
    fn batch_ast_rejects_invalid_thread_pool_config_on_hot_path() {
        let payload = json!({
            "files": [
                {"file_name": "A.js", "source": "const a = '日文';"}
            ]
        });

        let error =
            crate::native_core::pool::with_thread_count_override_for_test(Some("invalid"), || {
                parse_javascript_string_spans_batch_impl(&payload.to_string())
            })
            .expect_err("批量 JS AST 热路径必须读取并校验 runtime.rust_threads");

        assert!(
            error.contains("runtime.rust_threads 必须是正整数或 auto"),
            "错误文案应说明线程配置非法，实际为 {error}",
        );
    }
}
