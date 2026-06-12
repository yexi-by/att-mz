use super::models::PlannedFile;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

pub(super) fn build_changed_file(
    target_path: &Path,
    relative_path: &str,
    content: String,
) -> Result<Option<PlannedFile>, String> {
    if target_path.is_file() {
        let current = fs::read_to_string(target_path).map_err(|error| {
            if relative_path.starts_with("js/plugins/") {
                return format!("插件源码读取失败 {}: {error}", target_path.display());
            }
            format!("读取当前运行文件失败 {}: {error}", target_path.display())
        })?;
        if current == content {
            return Ok(None);
        }
    }
    Ok(Some(PlannedFile {
        target_path: target_path.display().to_string(),
        relative_path: relative_path.to_string(),
        content: Some(content),
        content_path: None,
    }))
}

pub(super) fn externalize_planned_file_contents(
    files: &mut [PlannedFile],
    output_dir_text: &str,
) -> Result<(), String> {
    let trimmed_output_dir = output_dir_text.trim();
    if trimmed_output_dir.is_empty() {
        return Err("写回计划 content 输出目录不能为空".to_string());
    }
    let output_dir = Path::new(trimmed_output_dir);
    if !output_dir.is_absolute() {
        return Err(format!(
            "写回计划 content 输出目录必须是绝对路径: {trimmed_output_dir}"
        ));
    }
    fs::create_dir_all(output_dir).map_err(|error| {
        format!(
            "写回计划 content 输出目录创建失败 {}: {error}",
            output_dir.display()
        )
    })?;
    for (index, file) in files.iter_mut().enumerate() {
        let content = file
            .content
            .take()
            .ok_or_else(|| format!("写回计划文件缺少可输出内容: {}", file.relative_path))?;
        let content_path = output_dir.join(format!("{index:06}.txt"));
        fs::write(&content_path, content).map_err(|error| {
            format!(
                "写回计划 content 写入失败 {}: {error}",
                content_path.display()
            )
        })?;
        file.content_path = Some(content_path.display().to_string());
    }
    Ok(())
}

pub(super) fn is_map_file(file_name: &str) -> bool {
    file_name.len() == 11
        && file_name.starts_with("Map")
        && file_name.ends_with(".json")
        && file_name[3..6].chars().all(|char| char.is_ascii_digit())
}

pub(super) fn sha256_text(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())
}

pub(super) fn sha256_translation_lines(lines: &[String]) -> Result<String, String> {
    let payload = serde_json::to_string(lines)
        .map_err(|error| format!("译文行哈希 JSON 编码失败: {error}"))?;
    Ok(sha256_text(&payload))
}

pub(super) fn current_timestamp_text() -> Result<String, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs().to_string())
        .map_err(|error| format!("系统时间早于 UNIX_EPOCH，不能生成运行映射时间戳: {error}"))
}

pub(super) fn render_format_template(
    template: &str,
    values: &HashMap<String, String>,
) -> Result<String, String> {
    let chars: Vec<char> = template.chars().collect();
    let mut rendered = String::new();
    let mut index = 0usize;
    while index < chars.len() {
        let current = chars[index];
        if current == '{' {
            if index + 1 < chars.len() && chars[index + 1] == '{' {
                rendered.push('{');
                index += 2;
                continue;
            }
            let mut end_index = index + 1;
            while end_index < chars.len() && chars[end_index] != '}' {
                end_index += 1;
            }
            if end_index >= chars.len() {
                return Err(format!("MV 虚拟名字框模板缺少右花括号: {template}"));
            }
            let field_name: String = chars[index + 1..end_index].iter().collect();
            let value = values
                .get(&field_name)
                .ok_or_else(|| format!("MV 虚拟名字框模板引用未知字段: {field_name}"))?;
            rendered.push_str(value);
            index = end_index + 1;
            continue;
        }
        if current == '}' {
            if index + 1 < chars.len() && chars[index + 1] == '}' {
                rendered.push('}');
                index += 2;
                continue;
            }
            return Err(format!("MV 虚拟名字框模板存在孤立右花括号: {template}"));
        }
        rendered.push(current);
        index += 1;
    }
    Ok(rendered)
}

pub(super) fn parse_usize(text: &str, context: &str) -> Result<usize, String> {
    text.parse::<usize>()
        .map_err(|error| format!("{context}: 数字解析失败 {text}: {error}"))
}

pub(super) fn parse_i64(text: &str, context: &str) -> Result<i64, String> {
    text.parse::<i64>()
        .map_err(|error| format!("{context}: 数字解析失败 {text}: {error}"))
}
