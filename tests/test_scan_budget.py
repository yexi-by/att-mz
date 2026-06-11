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


def test_external_regex_runtime_has_only_current_rule_runtime_entrypoints() -> None:
    """外部正则运行时只保留当前 rule_runtime 入口和 PCRE2 依赖。"""
    assert not Path("app/regex_contract.py").exists()
    assert not Path("rust/src/native_core/regex_contract.rs").exists()
    assert "fancy-regex" not in Path("rust/Cargo.toml").read_text(encoding="utf-8")


def test_no_python_external_regex_runtime_remains() -> None:
    """Python 运行时代码不得再执行用户/Agent 可写规则正则。"""
    files = [path for path in Path("app").rglob("*.py") if "__pycache__" not in path.parts]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    forbidden = [
        "validate_text_rules_regex_contract",
        "validate_mv_virtual_namebox_regex_contract",
        "validate_source_residual_regex_contract",
        "re.compile(record.pattern_text)",
        "rule.pattern.finditer",
        "rule.pattern.search",
        "rule.pattern.fullmatch",
    ]
    for needle in forbidden:
        assert needle not in combined


def test_no_python_rule_store_write_api_remains() -> None:
    """规则导入写库主路径不得保留 Python 第二事实源。"""
    files = [path for path in Path("app").rglob("*.py") if "__pycache__" not in path.parts]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    forbidden = [
        "def replace_plugin_text_rules",
        "def replace_plugin_source_text_rules",
        "def replace_nonstandard_data_text_rules",
        "def replace_note_tag_text_rules",
        "def replace_event_command_text_rules",
        "def replace_placeholder_rules",
        "def replace_structured_placeholder_rules",
        "def replace_source_residual_rules",
        "def replace_mv_virtual_namebox_rules",
        "def replace_rule_review_state",
        "def delete_rule_review_state",
        "RuleImport" + "UnitOfWork",
        "UPSERT_RULE" + "_SET",
        "UPSERT_RULE" + "_REVIEW_STATE",
        "DELETE_RULES" + "_BY_DOMAIN",
    ]
    for needle in forbidden:
        assert needle not in combined


def test_user_rule_fixtures_use_current_pcre2_named_capture_syntax() -> None:
    """当前测试、规格和 Skill 示例不得继续把 Python/Rust 交集写法当推荐契约。"""
    roots = [
        Path("tests"),
        Path("docs/superpowers/specs"),
        Path("skills"),
        Path("setting.example.toml"),
    ]
    old_named_capture = "(?P" + "<"
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        if root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.suffix in {".py", ".md", ".toml"}
                and "__pycache__" not in path.parts
            )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert old_named_capture not in combined


def test_source_text_required_pattern_stays_on_pcre2_runtime() -> None:
    """Rust 热路径不得用 regex crate 执行配置中的源文识别正则。"""
    files = [path for path in Path("rust/src/native_core").rglob("*.rs")]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    forbidden = [
        "Regex::new(&payload.source_text_required_pattern)",
        "Regex::new(&text_rules.source_text_required_pattern)",
        "source_text_required_re: Regex",
    ]
    for needle in forbidden:
        assert needle not in combined
