//! PCRE2 engine wrapper for user-authored and Agent-authored rule patterns.
//!
//! The high-level `pcre2` crate exposes JIT controls but not PCRE2
//! match/depth/heap limits. Resource guardrails for rule execution must remain
//! centralized in the rule runtime scheduler and candidate selection layer.

use pcre2::bytes::{Regex, RegexBuilder};
use std::{collections::BTreeMap, str};

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Pcre2EngineConfig {
    pub(crate) jit: bool,
}

impl Pcre2EngineConfig {
    pub(crate) fn default_runtime() -> Self {
        Self { jit: true }
    }

    #[cfg(test)]
    pub(crate) fn for_test() -> Self {
        Self::default_runtime()
    }
}

#[derive(Debug)]
pub(crate) struct Pcre2Engine;

impl Pcre2Engine {
    pub(crate) fn compile(
        pattern: &str,
        config: &Pcre2EngineConfig,
    ) -> Result<Pcre2Pattern, Pcre2EngineError> {
        let mut builder = RegexBuilder::new();
        builder.utf(true).ucp(true).jit(config.jit);
        let regex = builder.build(pattern).map_err(Pcre2EngineError::compile)?;

        Ok(Pcre2Pattern { regex })
    }
}

#[derive(Debug, Clone)]
pub(crate) struct Pcre2Pattern {
    regex: Regex,
}

impl Pcre2Pattern {
    pub(crate) fn is_match(&self, text: &str) -> Result<bool, Pcre2EngineError> {
        self.regex
            .is_match(text.as_bytes())
            .map_err(Pcre2EngineError::matching)
    }

    pub(crate) fn captures(&self, text: &str) -> Result<Option<Pcre2Captures>, Pcre2EngineError> {
        let Some(captures) = self
            .regex
            .captures(text.as_bytes())
            .map_err(Pcre2EngineError::matching)?
        else {
            return Ok(None);
        };

        let mut named = BTreeMap::new();
        for name in self.regex.capture_names().iter().flatten() {
            if let Some(matched) = captures.name(name) {
                let value =
                    str::from_utf8(matched.as_bytes()).map_err(Pcre2EngineError::capture_utf8)?;
                named.insert(name.clone(), value.to_owned());
            }
        }

        Ok(Some(Pcre2Captures { named }))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Pcre2Captures {
    named: BTreeMap<String, String>,
}

impl Pcre2Captures {
    pub(crate) fn named(&self, name: &str) -> Option<&str> {
        self.named.get(name).map(String::as_str)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Pcre2EngineError {
    pub(crate) code: &'static str,
    pub(crate) message: String,
}

impl Pcre2EngineError {
    fn compile(error: pcre2::Error) -> Self {
        Self {
            code: "pcre2_compile_error",
            message: format!("pattern 不是有效的 PCRE2 正则：{error}"),
        }
    }

    fn matching(error: pcre2::Error) -> Self {
        Self {
            code: "pcre2_match_error",
            message: format!("PCRE2 正则匹配失败：{error}"),
        }
    }

    fn capture_utf8(error: str::Utf8Error) -> Self {
        Self {
            code: "pcre2_capture_utf8_error",
            message: format!("PCRE2 命名捕获不是有效的 UTF-8 文本：{error}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pcre2_engine_extracts_named_capture_with_current_syntax() {
        let config = Pcre2EngineConfig::for_test();
        let pattern = Pcre2Engine::compile("^(?<speaker>[^:]+):(?<body>.*)$", &config)
            .expect("PCRE2 pattern should compile");

        let matched = pattern
            .captures("Alice:hello")
            .expect("matching should not fail")
            .expect("pattern should match");

        assert_eq!(matched.named("speaker"), Some("Alice"));
        assert_eq!(matched.named("body"), Some("hello"));
    }

    #[test]
    fn pcre2_engine_accepts_inline_flags() {
        let config = Pcre2EngineConfig::for_test();
        let pattern = Pcre2Engine::compile("(?i)^abc$", &config)
            .expect("inline ignore-case flag should compile");

        assert!(pattern.is_match("ABC").expect("matching should not fail"));
    }

    #[test]
    fn pcre2_engine_reports_invalid_pattern_with_field_context() {
        let config = Pcre2EngineConfig::for_test();
        let error =
            Pcre2Engine::compile("(?<speaker>", &config).expect_err("invalid PCRE2 should fail");

        assert_eq!(error.code, "pcre2_compile_error");
        assert!(error.message.contains("pattern 不是有效的 PCRE2 正则"));
    }
}
