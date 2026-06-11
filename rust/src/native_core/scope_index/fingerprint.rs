//! Scope/Index 内部稳定指纹工具。

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub(super) fn stable_json_fingerprint(value: &Value) -> Result<String, String> {
    let mut hasher = Sha256::new();
    update_canonical_json_hash(value, &mut hasher)?;
    Ok(hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn update_canonical_json_hash(value: &Value, hasher: &mut Sha256) -> Result<(), String> {
    match value {
        Value::Array(items) => {
            hasher.update(b"[");
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    hasher.update(b",");
                }
                update_canonical_json_hash(item, hasher)?;
            }
            hasher.update(b"]");
            Ok(())
        }
        Value::Object(object) => {
            hasher.update(b"{");
            let keys = object.keys().collect::<BTreeSet<_>>();
            for (index, key) in keys.into_iter().enumerate() {
                if index > 0 {
                    hasher.update(b",");
                }
                let encoded_key = serde_json::to_string(key)
                    .map_err(|error| format!("生成稳定 JSON 指纹失败: {error}"))?;
                hasher.update(encoded_key.as_bytes());
                hasher.update(b":");
                if let Some(child) = object.get(key) {
                    update_canonical_json_hash(child, hasher)?;
                }
            }
            hasher.update(b"}");
            Ok(())
        }
        _ => {
            let encoded = serde_json::to_string(value)
                .map_err(|error| format!("生成稳定 JSON 指纹失败: {error}"))?;
            hasher.update(encoded.as_bytes());
            Ok(())
        }
    }
}
