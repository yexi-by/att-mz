//! 受限括号 JSONPath 模板解析。

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) enum JsonPathPart {
    Key(String),
    Index(usize),
    Wildcard,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct PathTemplateError {
    pub(super) code: &'static str,
    pub(super) message: String,
}

pub(super) const PATH_TEMPLATE_INVALID_CODE: &str = "path_template_invalid";

pub(super) fn parse_json_path(path: &str) -> Result<Vec<JsonPathPart>, PathTemplateError> {
    let chars = path.chars().collect::<Vec<_>>();
    if chars.first() != Some(&'$') {
        return Err(path_template_error(path));
    }
    let mut index = 1;
    let mut parts = Vec::new();
    while index < chars.len() {
        if chars[index] != '[' {
            return Err(path_template_error(path));
        }
        index += 1;
        if index >= chars.len() {
            return Err(path_template_error(path));
        }
        if chars[index] == '\'' {
            index += 1;
            let mut key = String::new();
            while index < chars.len() {
                let current = chars[index];
                if current == '\\' {
                    index += 1;
                    if index >= chars.len() {
                        return Err(path_template_error(path));
                    }
                    key.push(chars[index]);
                    index += 1;
                    continue;
                }
                if current == '\'' {
                    index += 1;
                    if index >= chars.len() || chars[index] != ']' {
                        return Err(path_template_error(path));
                    }
                    index += 1;
                    parts.push(JsonPathPart::Key(key));
                    break;
                }
                key.push(current);
                index += 1;
            }
            if !matches!(parts.last(), Some(JsonPathPart::Key(_))) {
                return Err(path_template_error(path));
            }
            continue;
        }
        let start_index = index;
        while index < chars.len() && chars[index] != ']' {
            index += 1;
        }
        if index >= chars.len() {
            return Err(path_template_error(path));
        }
        let segment = chars[start_index..index].iter().collect::<String>();
        index += 1;
        if segment == "*" {
            parts.push(JsonPathPart::Wildcard);
            continue;
        }
        let parsed_index = segment
            .parse::<usize>()
            .map_err(|_error| path_template_error(path))?;
        parts.push(JsonPathPart::Index(parsed_index));
    }
    if parts.is_empty() {
        return Err(path_template_error(path));
    }
    Ok(parts)
}

pub(super) fn parse_json_path_message(path: &str) -> Result<Vec<JsonPathPart>, String> {
    parse_json_path(path).map_err(|error| error.message)
}

pub(super) fn jsonpath_matches_template(
    template_parts: &[JsonPathPart],
    actual_parts: &[JsonPathPart],
) -> bool {
    if template_parts.len() != actual_parts.len() {
        return false;
    }
    template_parts.iter().zip(actual_parts).all(
        |(template_part, actual_part)| match template_part {
            JsonPathPart::Wildcard => matches!(actual_part, JsonPathPart::Index(_)),
            _ => template_part == actual_part,
        },
    )
}

pub(super) fn json_path_parts_to_slash_path(parts: &[JsonPathPart]) -> Result<String, String> {
    Ok(json_path_parts_to_segments(parts)?.join("/"))
}

pub(super) fn json_path_parts_to_parent_slash_path(
    parts: &[JsonPathPart],
) -> Result<String, String> {
    let mut segments = json_path_parts_to_segments(parts)?;
    let _ = segments.pop();
    Ok(segments.join("/"))
}

fn json_path_parts_to_segments(parts: &[JsonPathPart]) -> Result<Vec<String>, String> {
    let mut segments = Vec::new();
    for part in parts {
        match part {
            JsonPathPart::Key(key) => segments.push(key.clone()),
            JsonPathPart::Index(index) => segments.push(index.to_string()),
            JsonPathPart::Wildcard => {
                return Err("JSONPath 实际路径不能包含通配符".to_string());
            }
        }
    }
    Ok(segments)
}

fn path_template_error(path: &str) -> PathTemplateError {
    PathTemplateError {
        code: PATH_TEMPLATE_INVALID_CODE,
        message: format!("JSONPath 超出当前规则范围: {path}"),
    }
}
