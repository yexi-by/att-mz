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
    })
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
