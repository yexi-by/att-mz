//! JavaScript AST 字符串节点扫描。
//!
//! 本模块只解析源码并返回稳定范围，不判断游戏私有语义。

use serde::{Deserialize, Serialize};
use tree_sitter::{Node, Parser};

#[derive(Debug, Deserialize)]
struct JavaScriptAstPayload {
    source: String,
}

#[derive(Debug, Serialize)]
struct JavaScriptStringSpan {
    kind: String,
    quote: String,
    start_index: usize,
    end_index: usize,
    content_start_index: usize,
    content_end_index: usize,
    ast_context: JavaScriptStringAstContext,
}

#[derive(Debug, Serialize)]
struct JavaScriptStringAstContext {
    node_kind: String,
    property_key: String,
    property_path: Vec<String>,
    call_name: String,
    call_argument_index: Option<usize>,
    return_function_name: String,
    assignment_name: String,
}

#[derive(Debug, Serialize)]
struct JavaScriptAstOutput {
    has_error: bool,
    spans: Vec<JavaScriptStringSpan>,
}

pub(crate) fn parse_javascript_string_spans_impl(payload_json: &str) -> Result<String, String> {
    let payload: JavaScriptAstPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("JS AST 输入不是有效 JSON: {error}"))?;
    let mut parser = Parser::new();
    let language = tree_sitter_javascript::LANGUAGE;
    parser
        .set_language(&language.into())
        .map_err(|error| format!("JS AST 语言初始化失败: {error}"))?;
    let tree = parser
        .parse(&payload.source, None)
        .ok_or_else(|| "JS AST 解析失败".to_string())?;
    let root = tree.root_node();
    let mut spans: Vec<JavaScriptStringSpan> = Vec::new();
    collect_string_nodes(root, &payload.source, &mut spans);
    let output = JavaScriptAstOutput {
        has_error: root.has_error(),
        spans,
    };
    serde_json::to_string(&output).map_err(|error| format!("JS AST 输出 JSON 失败: {error}"))
}

fn collect_string_nodes(node: Node<'_>, source: &str, spans: &mut Vec<JavaScriptStringSpan>) {
    if node.kind() == "string"
        && let Some(span) = build_string_span(node, source)
    {
        spans.push(span);
    }
    if node.kind() == "string_fragment"
        && node
            .parent()
            .is_some_and(|parent| parent.kind() == "template_string")
        && let Some(span) = build_template_fragment_span(node, source)
    {
        spans.push(span);
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_string_nodes(child, source, spans);
    }
}

fn build_string_span(node: Node<'_>, source: &str) -> Option<JavaScriptStringSpan> {
    let start_byte = node.start_byte();
    let end_byte = node.end_byte();
    let raw = source.get(start_byte..end_byte)?;
    let quote = raw.chars().next()?;
    if quote != '\'' && quote != '"' {
        return None;
    }
    let start_index = byte_to_char_index(source, start_byte)?;
    let end_index = byte_to_char_index(source, end_byte)?;
    if end_index <= start_index + 1 {
        return None;
    }
    Some(JavaScriptStringSpan {
        kind: node.kind().to_string(),
        quote: quote.to_string(),
        start_index,
        end_index,
        content_start_index: start_index + 1,
        content_end_index: end_index - 1,
        ast_context: build_ast_context(node, source),
    })
}

fn build_template_fragment_span(node: Node<'_>, source: &str) -> Option<JavaScriptStringSpan> {
    let start_index = byte_to_char_index(source, node.start_byte())?;
    let end_index = byte_to_char_index(source, node.end_byte())?;
    if end_index <= start_index {
        return None;
    }
    Some(JavaScriptStringSpan {
        kind: "template_fragment".to_string(),
        quote: "`".to_string(),
        start_index,
        end_index,
        content_start_index: start_index,
        content_end_index: end_index,
        ast_context: build_ast_context(node, source),
    })
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

fn byte_to_char_index(source: &str, byte_index: usize) -> Option<usize> {
    if byte_index > source.len() || !source.is_char_boundary(byte_index) {
        return None;
    }
    Some(source[..byte_index].chars().count())
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
}
