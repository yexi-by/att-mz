"""扫描预算与规则解释边界测试。"""

from pathlib import Path


def test_scope_index_no_longer_compiles_external_rule_regex() -> None:
    """scope index 不再直接解释用户/Agent 可写规则正则。"""
    rust_files = [
        Path("rust/src/native_core/scope_index/rebuild.rs"),
        Path("rust/src/native_core/scope_index/mv_virtual_namebox.rs"),
        Path("rust/src/native_core/scope_index/placeholders.rs"),
        Path("rust/src/native_core/scope_index/structured_placeholders.rs"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in rust_files)

    assert "fancy_regex" not in combined
    assert "FancyRegex" not in combined
    assert "Regex::new(&rule.pattern_text)" not in combined
    assert "Pcre2Engine::compile(&rule.pattern_text" not in combined
