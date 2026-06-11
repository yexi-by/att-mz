"""当前 PCRE2 规则运行时契约测试。"""

from app.native_rule_runtime import evaluate_runtime_config_patterns, prepare_rule_import
from app.rmmz.json_types import JsonObject


def _valid_runtime_patterns() -> JsonObject:
    """返回当前 rule_runtime 必需的配置正则。"""
    return {
        "source_text_required_pattern": r"[ぁ-んァ-ヶ一-龯ー]+",
        "source_residual_segment_pattern": r"[ぁ-んァ-ヶー]+",
        "line_width_count_pattern": r"\S",
        "residual_escape_sequence_pattern": r"\\[nrt]",
    }


def test_pcre2_rule_runtime_reports_missing_mv_namebox_capture() -> None:
    """MV 虚拟名字框规则必须通过 PCRE2 命名捕获校验。"""
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "mv_virtual_namebox",
            "rules_payload": {
                "rules": [
                    {
                        "name": "bad",
                        "pattern": r"^(?<name>.+)$",
                        "speaker_group": "speaker",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}",
                    }
                ]
            },
            "game_context": {"engine_kind": "mv"},
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "mv_virtual_namebox_speaker_capture_missing"
    assert result.errors[0].field == "speaker_group"


def test_pcre2_rule_runtime_reports_placeholder_compile_error() -> None:
    """普通占位符规则无效时返回当前 PCRE2 错误结构。"""
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "placeholders",
            "rules_payload": {r"(?<control>": "[CUSTOM_CONTROL_{index}]"},
            "game_context": {},
            "settings_runtime_patterns": _valid_runtime_patterns(),
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "pcre2_compile_error"
    assert result.errors[0].field == "pattern"
    assert "PCRE2" in result.errors[0].message


def test_runtime_config_patterns_use_inline_flags() -> None:
    """配置正则的 flag 只通过 PCRE2 内联写法表达。"""
    patterns = _valid_runtime_patterns()
    patterns["source_text_required_pattern"] = r"(?i)^quest$"
    result = evaluate_runtime_config_patterns(
        {
            "settings_runtime_patterns": patterns,
            "texts": [
                {"id": "upper", "text": "QUEST"},
                {"id": "other", "text": "item"},
            ],
        }
    )

    assert result.status == "ok"
    assert not result.errors
    assert [entry.source_text_required for entry in result.entries] == [True, False]
