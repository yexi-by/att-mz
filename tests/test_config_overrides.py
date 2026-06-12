"""CLI 配置覆盖测试。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import LLM_API_KEY_ENV_NAME, LLM_BASE_URL_ENV_NAME, RUNTIME_RUST_THREADS_ENV_NAME
from app.config import SettingOverrides
from app.utils import config_loader_utils
from app.utils.config_loader_utils import load_setting

ROOT = Path(__file__).resolve().parents[1]
MINIMAL_PROMPT_TEMPLATE = """系统提示词
字段：{{输出字段列表}}
规则：{{原文对照规则}}
示例：
{{原文对照示例行}}
"""


@pytest.fixture(autouse=True)
def clear_runtime_rust_threads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置覆盖测试默认不继承开发机 Rust 线程环境变量。"""
    monkeypatch.delenv(RUNTIME_RUST_THREADS_ENV_NAME, raising=False)


def test_load_setting_applies_cli_overrides_without_reading_prompt_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 覆盖可以用具体值替代 `setting.toml` 中的提示词文件引用。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = tmp_path / "setting.toml"
    _ = setting_path.write_text(
        """
[llm]
base_url = "https://example.invalid"
api_key = "from-file"
model = "file-model"
timeout = 10

[translation_context]
token_size = 10
factor = 1.0
max_command_items = 1

[text_translation]
worker_count = 1
rpm = 10
retry_count = 1
retry_delay = 1

[text_translation.system_prompt_files]
ja = "missing_prompt.txt"
en = "missing_prompt.txt"

[event_command_text.default_command_codes_by_engine]
mv = [356]
mz = [357]

[text_rules]
strip_wrapping_punctuation_pairs = [["「", "」"]]
source_residual_allowed_chars = ["っ"]
source_residual_allowed_tail_chars = ["ね"]
line_split_punctuations = ["。"]
long_text_line_width_limit = 30
line_width_count_pattern = "[\\u4E00-\\u9FFF]"
source_text_required_pattern = "[\\u3040-\\u30FF]+"
source_residual_segment_pattern = "[\\u3040-\\u30FF]+"
residual_escape_sequence_pattern = "\\\\[nrt]"
""",
        encoding="utf-8",
    )
    overrides = SettingOverrides(
        llm_model="cli-model",
        llm_timeout=600,
        translation_token_size=2048,
        translation_factor=4.0,
        translation_max_command_items=7,
        text_translation_worker_count=12,
        text_translation_rpm=None,
        text_translation_rpm_is_set=True,
        text_translation_retry_count=5,
        text_translation_retry_delay=3,
        text_translation_include_source_lines=True,
        text_translation_system_prompt=MINIMAL_PROMPT_TEMPLATE,
        strip_wrapping_punctuation_pairs=[("《", "》")],
        preserve_wrapping_punctuation_pairs=[("『", "』")],
        source_residual_allowed_chars=["ー"],
        source_residual_allowed_tail_chars=["よ"],
        line_split_punctuations=["，", "。"],
        long_text_line_width_limit=42,
        line_width_count_pattern="[a-z]",
        source_text_required_pattern="[ぁ-ん一-龠]+",
        source_residual_segment_pattern="[ぁ-ん]+",
        source_residual_detection_profile="english_source_copy",
        english_source_copy_min_words=2,
        english_source_copy_min_letters=6,
        residual_escape_sequence_pattern="\\\\[abc]",
        write_back_replacement_font_path="fonts/Override.ttf",
    )

    setting = load_setting(setting_path=setting_path, overrides=overrides)

    assert setting.llm.base_url == "https://example.invalid"
    assert setting.llm.api_key == "from-file"
    assert setting.llm.model == "cli-model"
    assert setting.llm.timeout == 600
    assert setting.translation_context.token_size == 2048
    assert setting.translation_context.factor == 4.0
    assert setting.translation_context.max_command_items == 7
    assert setting.text_translation.worker_count == 12
    assert setting.text_translation.rpm is None
    assert setting.text_translation.retry_count == 5
    assert setting.text_translation.retry_delay == 3
    assert setting.text_translation.include_source_lines is True
    assert setting.text_translation.selected_system_prompt_file == "<cli>"
    assert setting.text_translation.system_prompt.startswith("系统提示词")
    assert "`source_lines` 尽量原样复制输入原文，用于人工对照。" in setting.text_translation.system_prompt
    assert setting.text_rules.strip_wrapping_punctuation_pairs == [("《", "》")]
    assert setting.text_rules.preserve_wrapping_punctuation_pairs == [("『", "』")]
    assert setting.text_rules.source_residual_allowed_chars == ["ー"]
    assert setting.text_rules.source_residual_allowed_tail_chars == ["よ"]
    assert setting.text_rules.line_split_punctuations == ["，", "。"]
    assert setting.text_rules.long_text_line_width_limit == 42
    assert setting.text_rules.line_width_count_pattern == "[a-z]"
    assert setting.text_rules.source_text_required_pattern == "[ぁ-ん一-龠]+"
    assert setting.text_rules.source_residual_segment_pattern == "[ぁ-ん]+"
    assert setting.text_rules.source_residual_detection_profile == "english_source_copy"
    assert setting.text_rules.english_source_copy_min_words == 2
    assert setting.text_rules.english_source_copy_min_letters == 6
    assert setting.text_rules.residual_escape_sequence_pattern == "\\\\[abc]"
    assert setting.write_back.replacement_font_path == "fonts/Override.ttf"


def test_load_setting_reads_runtime_rust_thread_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 线程数必须从 setting.toml 的 runtime 段读取。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        runtime_text='[runtime]\nrust_threads = 8',
    )

    setting = load_setting(setting_path=setting_path)

    assert setting.runtime.rust_threads == 8


def test_setting_example_loads_debug_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """示例配置必须声明 debug 域，且完整业务配置加载后可读取默认 debug 设置。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(setting_path=ROOT / "setting.example.toml")

    assert setting.debug.enabled is False
    assert setting.debug.logging.enabled is True
    assert setting.debug.logging.console_level == "DEBUG"
    assert setting.debug.logging.file_level == "DEBUG"
    assert setting.debug.timings.enabled is True
    assert setting.debug.timings.write_file is True
    assert setting.debug.timings.include_summary_in_report is True
    assert setting.debug.timings.detail_level == "standard"
    assert setting.debug.llm_messages.enabled is True
    assert setting.debug.llm_messages.output_dir == "output/debug/llm-messages"


def test_debug_runtime_settings_uses_lightweight_config_and_cli_env_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """debug 运行配置只读取 [debug]，并按 CLI > env > setting > default 合并。"""
    from argparse import Namespace

    from app.observability.diagnostics import resolve_debug_runtime_settings

    setting_path = tmp_path / "setting.toml"
    _ = setting_path.write_text(
        """
[llm]
base_url = "https://example.invalid"
api_key = "from-file"
model = "file-model"
timeout = 10

[text_translation.system_prompt_files]
ja = "missing-ja-prompt.md"
en = "missing-en-prompt.md"

[debug]
enabled = false

[debug.logging]
enabled = false
console_level = "DEBUG"
file_level = "DEBUG"

[debug.timings]
enabled = false
write_file = true
include_summary_in_report = true
detail_level = "standard"

[debug.llm_messages]
enabled = false
output_dir = "debug/llm-messages"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_DEBUG", "1")
    monkeypatch.setenv("ATT_MZ_DEBUG_TIMINGS", "1")
    monkeypatch.setenv("ATT_MZ_DEBUG_LLM_MESSAGES", "1")
    args = Namespace(debug=None, debug_logging=True, debug_timings=None, debug_llm_messages=None)

    settings = resolve_debug_runtime_settings(args=args, setting_path=setting_path)

    assert settings.enabled is True
    assert settings.source == "env"
    assert settings.logging_enabled is True
    assert settings.logging_source == "cli"
    assert settings.timings_enabled is True
    assert settings.timings_source == "env"
    assert settings.llm_messages_enabled is True
    assert settings.llm_messages_source == "env"
    assert settings.llm_messages_output_dir == "debug/llm-messages"


def test_debug_runtime_settings_cli_overrides_llm_messages_env_and_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 消息观测子功能必须沿用 CLI > env > setting 优先级。"""
    from argparse import Namespace

    from app.observability.diagnostics import resolve_debug_runtime_settings

    setting_path = tmp_path / "setting.toml"
    _ = setting_path.write_text(
        """
[debug]
enabled = true

[debug.llm_messages]
enabled = true
output_dir = "custom/debug/llm"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_DEBUG_LLM_MESSAGES", "1")
    args = Namespace(
        debug=None,
        debug_logging=None,
        debug_timings=None,
        debug_llm_messages=False,
    )

    settings = resolve_debug_runtime_settings(args=args, setting_path=setting_path)

    assert settings.enabled is True
    assert settings.llm_messages_enabled is False
    assert settings.llm_messages_source == "cli"
    assert settings.effective_llm_messages_enabled is False
    assert settings.llm_messages_output_dir == "custom/debug/llm"


@pytest.mark.parametrize(
    ("runtime_text", "message"),
    [
        ("[runtime]\nrust_threads = 0", "runtime.rust_threads"),
        ("[runtime]\nrust_threads = -1", "runtime.rust_threads"),
        ('[runtime]\nrust_threads = ""', "runtime.rust_threads"),
        ('[runtime]\nrust_threads = "4"', "runtime.rust_threads"),
    ],
)
def test_load_setting_rejects_invalid_runtime_rust_thread_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime_text: str,
    message: str,
) -> None:
    """Rust 线程数只接受 auto 或正整数。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        runtime_text=runtime_text,
    )

    with pytest.raises(ValidationError, match=message):
        _ = load_setting(setting_path=setting_path)


def test_load_setting_configures_native_runtime_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置加载后必须把 Rust 线程设置应用到原生核心。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    configured_values: list[int | str] = []

    def fake_configure_native_runtime_threads(rust_threads: int | str) -> None:
        configured_values.append(rust_threads)

    monkeypatch.setattr(
        config_loader_utils,
        "configure_native_runtime_threads",
        fake_configure_native_runtime_threads,
    )
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        runtime_text='[runtime]\nrust_threads = "auto"',
    )

    _ = load_setting(setting_path=setting_path)

    assert configured_values == ["auto"]


def test_load_setting_applies_runtime_rust_threads_environment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ATT_MZ_RUST_THREADS 必须覆盖配置文件并传给原生核心。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    monkeypatch.setenv(RUNTIME_RUST_THREADS_ENV_NAME, "2")
    configured_values: list[int | str] = []

    def fake_configure_native_runtime_threads(rust_threads: int | str) -> None:
        configured_values.append(rust_threads)

    monkeypatch.setattr(
        config_loader_utils,
        "configure_native_runtime_threads",
        fake_configure_native_runtime_threads,
    )
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        runtime_text="[runtime]\nrust_threads = 8",
    )

    setting = load_setting(setting_path=setting_path)

    assert setting.runtime.rust_threads == 2
    assert configured_values == [2]


@pytest.mark.parametrize("raw_value", ["0", "-1", "many"])
def test_load_setting_rejects_invalid_runtime_rust_threads_environment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    """ATT_MZ_RUST_THREADS 非 auto/正整数时必须显式失败。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    monkeypatch.setenv(RUNTIME_RUST_THREADS_ENV_NAME, raw_value)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        runtime_text='[runtime]\nrust_threads = "auto"',
    )

    with pytest.raises(ValueError, match=RUNTIME_RUST_THREADS_ENV_NAME):
        _ = load_setting(setting_path=setting_path)


def test_load_setting_preserves_pcre2_text_rule_regex_for_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置加载只保留文本规则正则，PCRE2 编译由规则运行时统一执行。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(
        setting_path=ROOT / "setting.example.toml",
        overrides=SettingOverrides(line_width_count_pattern=r"(?<=a)b"),
    )

    assert setting.text_rules.line_width_count_pattern == r"(?<=a)b"


def test_load_setting_preserves_invalid_text_rule_regex_for_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置加载阶段不再保留第二套 Python re 校验事实源。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(
        setting_path=ROOT / "setting.example.toml",
        overrides=SettingOverrides(line_width_count_pattern="["),
    )

    assert setting.text_rules.line_width_count_pattern == "["


def test_english_language_profile_selects_public_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """英文语言档案会切换正文提示词，且不把内部定位字段暴露给模型。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(setting_path=ROOT / "setting.example.toml", source_language="en")
    system_prompt = setting.text_translation.system_prompt

    assert setting.text_translation.selected_system_prompt_file == "prompts/text_translation_en_to_zh_system.md"
    assert "RPG Maker 英文游戏" in system_prompt
    assert "location_path" not in system_prompt
    assert "translated_text" not in system_prompt
    assert "位置:" not in system_prompt
    assert "文件名" not in system_prompt


def test_japanese_language_profile_selects_explicit_public_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """日文语言档案使用能表达日文到中文含义的提示词文件名。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(setting_path=ROOT / "setting.example.toml", source_language="ja")
    system_prompt = setting.text_translation.system_prompt

    assert setting.text_translation.selected_system_prompt_file == "prompts/text_translation_ja_to_zh_system.md"
    assert "RPG Maker 日文到简体中文游戏" in system_prompt
    assert "text_translation_ja_to_zh_system.md" not in system_prompt


def test_default_output_protocol_disables_source_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认提示词要求模型不要输出原文对照字段。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(setting_path=ROOT / "setting.example.toml")
    system_prompt = setting.text_translation.system_prompt

    assert setting.text_translation.include_source_lines is False
    assert "每个数组元素必须包含 `id`、`role`、`translation_lines`" in system_prompt
    assert "不要输出 `source_lines`" in system_prompt
    assert "{{输出字段列表}}" not in system_prompt
    assert "本轮输出协议补充" not in system_prompt
    assert '"source_lines"' not in system_prompt


def test_builtin_prompt_template_can_enable_source_lines_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内置提示词模板开启后会在输出格式原位要求原文对照字段。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)

    setting = load_setting(
        setting_path=ROOT / "setting.example.toml",
        overrides=SettingOverrides(text_translation_include_source_lines=True),
    )
    system_prompt = setting.text_translation.system_prompt

    assert setting.text_translation.include_source_lines is True
    assert "每个数组元素必须包含 `id`、`role`、`source_lines`、`translation_lines`" in system_prompt
    assert '`source_lines` 尽量原样复制输入原文，用于人工对照。' in system_prompt
    assert '"source_lines": ["<输入原文>"],' in system_prompt
    assert "{{输出字段列表}}" not in system_prompt
    assert "本轮输出协议补充" not in system_prompt


def test_custom_prompt_without_template_appends_output_protocol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自定义提示词缺少模板时自动追加当前输出协议。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        text_translation_extra="include_source_lines = true",
        prompt_text="系统提示词",
    )

    setting = load_setting(setting_path=setting_path)

    assert setting.text_translation.include_source_lines is True
    assert setting.text_translation.system_prompt.startswith("系统提示词")
    assert "本轮输出协议补充" in setting.text_translation.system_prompt
    assert "每个 JSON 数组元素必须包含 `id`、`role`、`source_lines`、`translation_lines`" in setting.text_translation.system_prompt
    assert "`source_lines` 尽量原样复制输入原文，用于人工对照。" in setting.text_translation.system_prompt
    assert "location_path" not in setting.text_translation.system_prompt


def test_custom_prompt_partial_template_fails_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自定义提示词只写了部分模板占位符时显式失败，避免半套协议。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        prompt_text="系统提示词 {{输出字段列表}}",
    )

    with pytest.raises(ValueError, match="正文翻译提示词模板缺少必要占位符"):
        _ = load_setting(setting_path=setting_path)


def test_unknown_text_translation_setting_key_fails_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前配置模型遇到未知正文翻译字段时必须显式失败。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = tmp_path / "setting.toml"
    _ = setting_path.write_text(
        """
[llm]
base_url = "https://example.invalid"
api_key = "from-file"
model = "file-model"
timeout = 10

[translation_context]
token_size = 10
factor = 1.0
max_command_items = 1

[text_translation]
worker_count = 1
rpm = 10
retry_count = 1
retry_delay = 1
unknown_prompt_key = "prompt.txt"

[text_translation.system_prompt_files]
ja = "prompt.txt"
en = "prompt.txt"

[event_command_text.default_command_codes_by_engine]
mv = [356]
mz = [357]
""",
        encoding="utf-8",
    )
    _ = (tmp_path / "prompt.txt").write_text(MINIMAL_PROMPT_TEMPLATE, encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        _ = load_setting(setting_path=setting_path)
    message = str(exc_info.value)
    assert "unknown_prompt_key" in message
    assert "Extra inputs are not permitted" in message or "额外输入" in message


def test_custom_prompt_template_can_enable_source_lines_protocol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自定义提示词模板开启后会在原位要求原文对照字段。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="",
        text_translation_extra="include_source_lines = true",
    )

    setting = load_setting(setting_path=setting_path)

    assert setting.text_translation.include_source_lines is True
    assert setting.text_translation.system_prompt.startswith("系统提示词")
    assert "`source_lines` 尽量原样复制输入原文，用于人工对照。" in setting.text_translation.system_prompt
    assert "本轮输出协议补充" not in setting.text_translation.system_prompt


def test_default_prompt_files_do_not_request_source_lines() -> None:
    """默认提示词文件不要求模型回传原文，开关补充负责动态声明。"""
    prompt_paths = [
        ROOT / "prompts" / "text_translation_ja_to_zh_system.md",
        ROOT / "prompts" / "text_translation_en_to_zh_system.md",
    ]

    for prompt_path in prompt_paths:
        text = prompt_path.read_text(encoding="utf-8")
        assert "{{输出字段列表}}" in text
        assert "{{原文对照规则}}" in text
        assert "{{原文对照示例行}}" in text
        assert "`source_lines`" not in text
        assert '"source_lines"' not in text


def test_load_setting_applies_environment_llm_connection_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量优先覆盖模型地址和密钥。"""
    setting_path = tmp_path / "setting.toml"
    _ = setting_path.write_text(
        """
[llm]
base_url = "https://example.invalid"
api_key = "from-file"
model = "file-model"
timeout = 10

[translation_context]
token_size = 10
factor = 1.0
max_command_items = 1

[text_translation]
worker_count = 1
rpm = 10
retry_count = 1
retry_delay = 1

[text_translation.system_prompt_files]
ja = "prompt.txt"
en = "prompt.txt"

[event_command_text.default_command_codes_by_engine]
mv = [356]
mz = [357]
""",
        encoding="utf-8",
    )
    _ = (tmp_path / "prompt.txt").write_text(MINIMAL_PROMPT_TEMPLATE, encoding="utf-8")
    monkeypatch.setenv(LLM_BASE_URL_ENV_NAME, "https://env.example.com")
    monkeypatch.setenv(LLM_API_KEY_ENV_NAME, "env-key")

    setting = load_setting(setting_path=setting_path)

    assert setting.llm.base_url == "https://env.example.com"
    assert setting.llm.api_key == "env-key"
    assert setting.llm.model == "file-model"


def test_unknown_llm_setting_key_is_reported_as_current_invalid_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前配置模型遇到未知 LLM 字段时必须显式失败。"""
    setting_path = _write_minimal_setting(tmp_path, request_body_extra_text="")
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    text = setting_path.read_text(encoding="utf-8")
    _ = setting_path.write_text(
        text.replace(
            'timeout = 10\n',
            'timeout = 10\nunknown_key = "value"\n',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        _ = load_setting(setting_path=setting_path)
    message = str(exc_info.value)
    assert "unknown_key" in message
    assert "Extra inputs are not permitted" in message or "额外输入" in message


def test_load_setting_accepts_llm_request_body_extra_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型请求体额外参数可以用 JSON 对象字符串配置。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text="""
request_body_extra = '''
{
  "reasoning_effort": "high",
  "thinking": {"type": "enabled"},
  "max_completion_tokens": 2048
}
'''
""",
    )

    setting = load_setting(setting_path=setting_path)

    assert setting.llm.request_body_extra == {
        "reasoning_effort": "high",
        "thinking": {"type": "enabled"},
        "max_completion_tokens": 2048,
    }


@pytest.mark.parametrize(
    "request_body_extra_text",
    [
        'request_body_extra = \'\'\'{"stream": true}\'\'\'',
        'request_body_extra = \'\'\'{"stream_options": {"include_usage": true}}\'\'\'',
    ],
)
def test_load_setting_rejects_streaming_llm_request_body_extra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_body_extra_text: str,
) -> None:
    """模型请求体额外参数启用流式返回时必须说明原因并停止加载。"""
    monkeypatch.delenv(LLM_BASE_URL_ENV_NAME, raising=False)
    monkeypatch.delenv(LLM_API_KEY_ENV_NAME, raising=False)
    setting_path = _write_minimal_setting(
        tmp_path,
        request_body_extra_text=request_body_extra_text,
    )

    with pytest.raises(ValidationError, match="当前不支持 LLM 流式返回"):
        _ = load_setting(setting_path=setting_path)


def _write_minimal_setting(
    tmp_path: Path,
    *,
    request_body_extra_text: str,
    text_translation_extra: str = "",
    prompt_text: str = MINIMAL_PROMPT_TEMPLATE,
    runtime_text: str = "",
) -> Path:
    """写入只包含配置加载测试所需字段的设置文件。"""
    setting_path = tmp_path / "setting.toml"
    _ = (tmp_path / "prompt.txt").write_text(prompt_text, encoding="utf-8")
    _ = setting_path.write_text(
        f"""
[llm]
base_url = "https://example.invalid"
api_key = "from-file"
model = "file-model"
timeout = 10
{request_body_extra_text}

[translation_context]
token_size = 10
factor = 1.0
max_command_items = 1

[text_translation]
worker_count = 1
rpm = 10
retry_count = 1
retry_delay = 1
{text_translation_extra}

[text_translation.system_prompt_files]
ja = "prompt.txt"
en = "prompt.txt"

[event_command_text.default_command_codes_by_engine]
mv = [356]
mz = [357]

{runtime_text}
""",
        encoding="utf-8",
    )
    return setting_path
