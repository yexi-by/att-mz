# External Input Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立统一外部输入类型规范化边界，让游戏原文、Agent 导入数据和 LLM 翻译结果只在入口处允许 `int <-> str` 显式规范化。

**Architecture:** 新增 `app/external_input` 作为单一事实来源，提供严格 Pydantic 基类和显式字段类型。三类外部输入入口改用这些类型或同模块手写函数，业务内部模型、配置、CLI、环境变量、数据库记录和 native 契约不接入该层。

**Tech Stack:** Python 3.14、Pydantic v2 `Annotated`/`BeforeValidator`、pytest、basedpyright、uv。

---

## File Structure

- Create: `app/external_input/__init__.py`
  - 导出外部输入规范化类型和手写边界函数。
- Create: `app/external_input/types.py`
  - 定义 `ExternalInputModel`、`ExternalStr`、`ExternalInt`、`ExternalStrList` 和统一错误描述函数。
- Create: `tests/test_external_input.py`
  - 固定 `int <-> str` 转换矩阵和布尔/浮点拒绝行为。
- Modify: `app/translation/verify.py`
  - LLM 响应模型改用外部输入类型；`TranslationResponseItem` 显式忽略模型多余字段。
- Modify: `tests/test_translation_line_alignment.py`
  - 更新 LLM 响应类型测试，当前契约改为数字 `id` 可规范化、布尔 `id` 失败。
- Modify: `app/plugin_text/importer.py`
  - 插件规则导入模型改用外部输入类型。
- Modify: `app/event_command_text/importer.py`
  - 事件指令规则导入模型改用外部输入类型。
- Modify: `app/plugin_source_text/models.py`
  - 插件源码规则导入模型改用外部输入类型。
- Modify: `app/note_tag_text/importer.py`
  - Note 标签规则 TypeAdapter 改用外部字符串类型。
- Modify: `app/nonstandard_data/rules.py`
  - 非标准 data 规则导入模型改用外部输入类型，`skipped` 保持真实布尔。
- Modify: `app/source_residual/rules.py`
  - 源文残留规则导入模型改用外部输入类型。
- Modify: `app/rmmz/mv_namebox.py`
  - MV 虚拟名字框规则导入模型改用外部输入类型。
- Modify: `app/agent_toolkit/services/manual_translation.py`
  - 手动译文导入的 `fact_id` 和 `translation_lines` 使用统一手写规范化函数。
- Modify: `app/agent_toolkit/services/common.py`
  - reset translations 和 feedback 文本清单使用统一手写规范化函数。
- Modify: `app/rmmz/game_data.py`
  - RPG Maker 标准 data 模型改用外部输入类型。
- Modify: `app/rmmz/loader.py`
  - `MapInfos.json` id 检查使用同一整数规范化函数。
- Test: `tests/test_agent_toolkit_rule_import.py`
  - 覆盖插件规则和事件指令规则的字符串/整数规范化。
- Test: `tests/test_agent_toolkit_manual_import.py`
  - 覆盖手动译文 `translation_lines` 整数规范化和布尔拒绝。
- Test: `tests/test_agent_toolkit_feedback.py`
  - 覆盖反馈清单整数文本规范化和布尔拒绝。
- Test: `tests/test_game_data_external_input.py`
  - 覆盖游戏 data 模型和 `MapInfos.json` 的当前外部输入契约。

## Implementation Tasks

### Task 1: External Input Normalization Module

**Files:**
- Create: `app/external_input/__init__.py`
- Create: `app/external_input/types.py`
- Create: `tests/test_external_input.py`

- [ ] **Step 1: Write failing tests for the conversion matrix**

Create `tests/test_external_input.py`:

```python
"""外部输入类型规范化契约测试。"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.external_input import (
    ExternalInt,
    ExternalStr,
    normalize_external_int,
    normalize_external_str,
    normalize_external_str_list,
)


def test_external_str_accepts_string_and_integer() -> None:
    adapter = TypeAdapter(ExternalStr)

    assert adapter.validate_python("1") == "1"
    assert adapter.validate_python(1) == "1"
    assert normalize_external_str(2, "id") == "2"


@pytest.mark.parametrize("value", [True, False, 1.0, None, [], {}])
def test_external_str_rejects_non_string_integer_values(value: object) -> None:
    adapter = TypeAdapter(ExternalStr)

    with pytest.raises(ValidationError):
        _ = adapter.validate_python(value)


def test_external_int_accepts_integer_and_integer_string() -> None:
    adapter = TypeAdapter(ExternalInt)

    assert adapter.validate_python(1) == 1
    assert adapter.validate_python("1") == 1
    assert adapter.validate_python(" 12 ") == 12
    assert normalize_external_int("3", "plugin_index") == 3


@pytest.mark.parametrize("value", [True, False, 1.0, "1.0", "", " ", None, [], {}])
def test_external_int_rejects_non_integer_values(value: object) -> None:
    adapter = TypeAdapter(ExternalInt)

    with pytest.raises(ValidationError):
        _ = adapter.validate_python(value)


def test_external_string_list_reports_indexed_value() -> None:
    assert normalize_external_str_list(["a", 1], "translation_lines") == ["a", "1"]

    with pytest.raises(TypeError) as error_info:
        _ = normalize_external_str_list(["a", True], "translation_lines")

    message = str(error_info.value)
    assert "translation_lines[1]" in message
    assert "bool" in message
```

- [ ] **Step 2: Run the new tests and verify they fail because the module is absent**

Run:

```powershell
uv run pytest tests/test_external_input.py
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.external_input'`.

- [ ] **Step 3: Implement the external input module**

Create `app/external_input/types.py`:

```python
"""外部输入类型规范化工具。"""

from __future__ import annotations

import re
from typing import Annotated, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict

INTEGER_TEXT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")


class ExternalInputModel(BaseModel):
    """外部 JSON 输入模型基类，只允许显式字段类型执行规范化。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)


def describe_external_value(value: object) -> str:
    """返回适合外部输入错误信息的短类型描述。"""
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    if isinstance(value, str):
        return f'string: "{value}"'
    if isinstance(value, int):
        return f"integer: {value}"
    if isinstance(value, float):
        return f"float: {value}"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def normalize_external_str(value: object, field_label: str = "值") -> str:
    """把外部字符串字段规范化为 Python str。"""
    if isinstance(value, bool):
        raise TypeError(f"{field_label} 必须是字符串或整数，当前收到 {describe_external_value(value)}")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"{field_label} 必须是字符串或整数，当前收到 {describe_external_value(value)}")


def normalize_external_int(value: object, field_label: str = "值") -> int:
    """把外部整数字段规范化为 Python int。"""
    if isinstance(value, bool):
        raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value or INTEGER_TEXT_PATTERN.fullmatch(normalized_value) is None:
            raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")
        return int(normalized_value)
    raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")


def normalize_external_str_list(value: object, field_label: str) -> list[str]:
    """把外部字符串数组规范化为 Python str 列表。"""
    if not isinstance(value, list):
        raise TypeError(f"{field_label} 必须是字符串数组，当前收到 {describe_external_value(value)}")
    normalized_items: list[str] = []
    for index, item in enumerate(value):
        normalized_items.append(normalize_external_str(item, f"{field_label}[{index}]"))
    return normalized_items


ExternalStr = Annotated[str, BeforeValidator(normalize_external_str)]
ExternalInt = Annotated[int, BeforeValidator(normalize_external_int)]
ExternalStrList = list[ExternalStr]


__all__ = [
    "ExternalInputModel",
    "ExternalInt",
    "ExternalStr",
    "ExternalStrList",
    "describe_external_value",
    "normalize_external_int",
    "normalize_external_str",
    "normalize_external_str_list",
]
```

Create `app/external_input/__init__.py`:

```python
"""外部输入类型规范化公共出口。"""

from app.external_input.types import (
    ExternalInputModel,
    ExternalInt,
    ExternalStr,
    ExternalStrList,
    describe_external_value,
    normalize_external_int,
    normalize_external_str,
    normalize_external_str_list,
)

__all__ = [
    "ExternalInputModel",
    "ExternalInt",
    "ExternalStr",
    "ExternalStrList",
    "describe_external_value",
    "normalize_external_int",
    "normalize_external_str",
    "normalize_external_str_list",
]
```

- [ ] **Step 4: Run the new tests and verify they pass**

Run:

```powershell
uv run pytest tests/test_external_input.py
```

Expected: PASS, all tests in `tests/test_external_input.py` pass.

- [ ] **Step 5: Run type checking for the new module**

Run:

```powershell
uv run basedpyright app/external_input tests/test_external_input.py
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add app/external_input tests/test_external_input.py
git commit -m "feat: 添加外部输入类型规范化模块"
```

Expected: commit succeeds.

### Task 2: LLM Translation Response Normalization

**Files:**
- Modify: `app/translation/verify.py`
- Modify: `tests/test_translation_line_alignment.py`

- [ ] **Step 1: Update LLM response tests first**

In `tests/test_translation_line_alignment.py`, replace `test_translation_response_rejects_non_string_prompt_id` with:

```python
@pytest.mark.asyncio
async def test_translation_response_accepts_integer_prompt_id() -> None:
    """模型响应 ID 可以用整数表达当前批次临时 ID。"""
    text_rules = _build_text_rules(width_limit=40)
    item = TranslationItem(
        fact_id="fact-integer-id",
        location_path="Map001.json/1/0/0",
        item_type="long_text",
        role="村人",
        original_lines=["こんにちは"],
    )
    item.build_placeholders(text_rules)
    right_queue: asyncio.Queue[list[TranslationItem] | None] = asyncio.Queue()
    error_queue: asyncio.Queue[list[TranslationErrorItem] | None] = asyncio.Queue()

    await verify_translation_batch(
        ai_result=_build_model_response(
            item=item,
            prompt_id=1,
            translation_lines=["你好"],
        ),
        items=[item],
        prompt_ids_by_location_path={item.location_path: "1"},
        right_queue=right_queue,
        error_queue=error_queue,
        text_rules=text_rules,
    )

    assert error_queue.empty()
    right_items = await right_queue.get()
    assert right_items is not None
    assert right_items[0].translation_lines == ["你好"]
```

Add these tests near the same response parsing tests:

```python
@pytest.mark.asyncio
async def test_translation_response_rejects_boolean_prompt_id() -> None:
    """模型响应 ID 不能用布尔值表达。"""
    text_rules = _build_text_rules(width_limit=40)
    item = TranslationItem(
        fact_id="fact-boolean-id",
        location_path="Map001.json/1/0/0",
        item_type="long_text",
        role="村人",
        original_lines=["こんにちは"],
    )
    item.build_placeholders(text_rules)
    right_queue: asyncio.Queue[list[TranslationItem] | None] = asyncio.Queue()
    error_queue: asyncio.Queue[list[TranslationErrorItem] | None] = asyncio.Queue()

    await verify_translation_batch(
        ai_result=_build_model_response(
            item=item,
            prompt_id=True,
            translation_lines=["你好"],
        ),
        items=[item],
        prompt_ids_by_location_path={item.location_path: "1"},
        right_queue=right_queue,
        error_queue=error_queue,
        text_rules=text_rules,
    )

    assert right_queue.empty()
    error_items = await error_queue.get()
    assert error_items is not None
    assert error_items[0].error_type == "模型返回不可解析"
    assert "bool" in "\n".join(error_items[0].error_detail)


@pytest.mark.asyncio
async def test_translation_response_normalizes_integer_translation_line() -> None:
    """模型响应译文行中的整数按外部文本规范化为字符串。"""
    text_rules = _build_text_rules(width_limit=40)
    item = TranslationItem(
        fact_id="fact-integer-line",
        location_path="Map001.json/1/0/0",
        item_type="short_text",
        role=None,
        original_lines=["一"],
    )
    item.build_placeholders(text_rules)
    right_queue: asyncio.Queue[list[TranslationItem] | None] = asyncio.Queue()
    error_queue: asyncio.Queue[list[TranslationErrorItem] | None] = asyncio.Queue()

    await verify_translation_batch(
        ai_result=_build_model_response(
            item=item,
            prompt_id="1",
            translation_lines=[1],
        ),
        items=[item],
        prompt_ids_by_location_path={item.location_path: "1"},
        right_queue=right_queue,
        error_queue=error_queue,
        text_rules=text_rules,
    )

    assert error_queue.empty()
    right_items = await right_queue.get()
    assert right_items is not None
    assert right_items[0].translation_lines == ["1"]
```

- [ ] **Step 2: Run the updated LLM tests and verify the integer ID test fails**

Run:

```powershell
uv run pytest tests/test_translation_line_alignment.py::test_translation_response_accepts_integer_prompt_id tests/test_translation_line_alignment.py::test_translation_response_rejects_boolean_prompt_id tests/test_translation_line_alignment.py::test_translation_response_normalizes_integer_translation_line
```

Expected: at least `test_translation_response_accepts_integer_prompt_id` and `test_translation_response_normalizes_integer_translation_line` fail before implementation because current LLM 响应模型不接受整数作为字符串字段。After implementation, all three tests must pass.

- [ ] **Step 3: Update `app/translation/verify.py` response models**

Modify imports at the top of `app/translation/verify.py`:

```python
from typing import ClassVar

from json_repair import repair_json
from pydantic import ConfigDict, RootModel

from app.external_input import ExternalInputModel, ExternalStr
```

Replace the response item model with:

```python
class TranslationResponseItem(ExternalInputModel):
    """模型返回的单条对照译文。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", strict=True)

    id: ExternalStr
    translation_lines: list[ExternalStr]
```

Keep `TranslationResponse` as:

```python
class TranslationResponse(RootModel[list[TranslationResponseItem]]):
    """正文翻译返回结果模型。"""
```

- [ ] **Step 4: Run the LLM response tests and verify they pass**

Run:

```powershell
uv run pytest tests/test_translation_line_alignment.py::test_translation_response_accepts_integer_prompt_id tests/test_translation_line_alignment.py::test_translation_response_rejects_boolean_prompt_id tests/test_translation_line_alignment.py::test_translation_response_normalizes_integer_translation_line tests/test_translation_line_alignment.py::test_translation_response_ignores_source_lines_and_extra_fields
```

Expected: PASS. `test_translation_response_ignores_source_lines_and_extra_fields` must still pass because LLM extra fields are current external-output tolerance.

- [ ] **Step 5: Run focused translation tests**

Run:

```powershell
uv run pytest tests/test_translation_line_alignment.py tests/test_translation_cache_context.py tests/test_translation_run_limits.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add app/translation/verify.py tests/test_translation_line_alignment.py
git commit -m "fix: 规范化模型翻译响应外部类型"
```

Expected: commit succeeds.

### Task 3: Agent Rule Import Model Normalization

**Files:**
- Modify: `app/plugin_text/importer.py`
- Modify: `app/event_command_text/importer.py`
- Modify: `app/plugin_source_text/models.py`
- Modify: `app/note_tag_text/importer.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/source_residual/rules.py`
- Modify: `app/rmmz/mv_namebox.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Add failing rule import tests**

In `tests/test_agent_toolkit_rule_import.py`, add tests near existing plugin and event command rule import tests:

```python
def test_plugin_rule_import_accepts_integer_string_index() -> None:
    """插件规则 plugin_index 可以用整数字符串表达。"""
    import_file = parse_plugin_rule_import_text(
        """
        [
          {
            "plugin_index": "0",
            "plugin_name": 123,
            "paths": [1]
          }
        ]
        """
    )

    assert import_file[0].plugin_index == 0
    assert import_file[0].plugin_name == "123"
    assert import_file[0].paths == ["1"]


def test_plugin_rule_import_rejects_boolean_index() -> None:
    """插件规则 plugin_index 不能用布尔值表达。"""
    with pytest.raises(Exception) as error_info:
        _ = parse_plugin_rule_import_text(
            """
            [
              {
                "plugin_index": true,
                "plugin_name": "Plugin",
                "paths": ["parameters/name"]
              }
            ]
            """
        )

    assert "bool" in str(error_info.value)


def test_event_command_rule_import_normalizes_match_and_paths() -> None:
    """事件指令规则中的 match 值和路径可以用整数表达字符串。"""
    import_file = parse_event_command_rule_import_text(
        """
        {
          "357": [
            {
              "match": {"0": 123},
              "paths": [1]
            }
          ]
        }
        """
    )

    specs = import_file["357"]
    assert specs[0].match == {"0": "123"}
    assert specs[0].paths == ["1"]
```

Add these imports near the existing app imports in `tests/test_agent_toolkit_rule_import.py`:

```python
from app.event_command_text import parse_event_command_rule_import_text
from app.plugin_text import parse_plugin_rule_import_text
```

- [ ] **Step 2: Run the new rule import tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_plugin_rule_import_accepts_integer_string_index tests/test_agent_toolkit_rule_import.py::test_plugin_rule_import_rejects_boolean_index tests/test_agent_toolkit_rule_import.py::test_event_command_rule_import_normalizes_match_and_paths
```

Expected: at least the normalization tests fail before implementation.

- [ ] **Step 3: Update plugin rule import model**

In `app/plugin_text/importer.py`, replace Pydantic base imports and model base with:

```python
from pydantic import Field, TypeAdapter, field_validator

from app.external_input import ExternalInputModel, ExternalInt, ExternalStr
```

Use:

```python
class PluginRuleSpec(ExternalInputModel):
    """单个插件参数文本规则。"""

    plugin_index: ExternalInt = Field(ge=0)
    plugin_name: ExternalStr
    paths: list[ExternalStr] = Field(default_factory=list)
```

Delete `StrictPluginRuleModel` when no longer used.

- [ ] **Step 4: Update event command rule import model**

In `app/event_command_text/importer.py`, replace Pydantic base imports and model base with:

```python
from pydantic import Field, TypeAdapter, field_validator

from app.external_input import ExternalInputModel, ExternalStr
```

Use:

```python
class EventCommandRuleSpec(ExternalInputModel):
    """同一类事件指令参数文本规则。"""

    match: dict[ExternalStr, ExternalStr] = Field(default_factory=dict)
    paths: list[ExternalStr] = Field(default_factory=list)
```

Delete `StrictEventCommandRuleModel` when no longer used.

- [ ] **Step 5: Update plugin-source, note-tag, nonstandard-data, residual and MV namebox models**

In `app/plugin_source_text/models.py`, replace rule import models with:

```python
from app.external_input import ExternalInputModel, ExternalStr


class PluginSourceRuleImportEntry(ExternalInputModel):
    """插件源码规则导入文件中的单文件规则。"""

    file: ExternalStr
    selectors: list[ExternalStr] = Field(default_factory=list)
    excluded_selectors: list[ExternalStr] = Field(default_factory=list)


class PluginSourceRuleImportFile(ExternalInputModel):
    """插件源码规则导入文件。"""

    rules: list[PluginSourceRuleImportEntry] = Field(default_factory=list)
```

In `app/note_tag_text/importer.py`, import `ExternalStr` and update the alias:

```python
from app.external_input import ExternalStr

type NoteTagRuleImportFile = dict[ExternalStr, list[ExternalStr]]
```

In `app/nonstandard_data/rules.py`, use:

```python
from app.external_input import ExternalInputModel, ExternalStr


class NonstandardDataRuleSpec(ExternalInputModel):
    """单个非标准 data JSON 文件的文本规则。"""

    file: ExternalStr
    paths: list[ExternalStr] = Field(default_factory=list)
    excluded_paths: list[ExternalStr] = Field(default_factory=list)
    skipped: bool = False
```

In `app/source_residual/rules.py`, use:

```python
from app.external_input import ExternalInputModel, ExternalStr


class PositionSourceResidualRuleSpec(ExternalInputModel):
    """单个文本位置允许保留的源文片段。"""

    allowed_terms: list[ExternalStr] = Field(default_factory=list)
    reason: ExternalStr


class StructuralSourceResidualRuleSpec(ExternalInputModel):
    """结构性协议词保留规则。"""

    pattern: ExternalStr
    allowed_terms: list[ExternalStr] = Field(default_factory=list)
    check_group: ExternalStr
    reason: ExternalStr


class SourceResidualRuleImportFile(ExternalInputModel):
    """源文残留例外规则导入文件。"""

    position_rules: dict[ExternalStr, PositionSourceResidualRuleSpec] = Field(default_factory=dict)
    structural_rules: list[StructuralSourceResidualRuleSpec] = Field(default_factory=list)
```

In `app/rmmz/mv_namebox.py`, use:

```python
from app.external_input import ExternalInputModel, ExternalStr


class MvVirtualNameboxRuleSpec(ExternalInputModel):
    """单条 MV 虚拟名字框外部规则。"""

    name: ExternalStr
    pattern: ExternalStr
    speaker_group: ExternalStr
    speaker_policy: MvVirtualNameboxSpeakerPolicy
    render_template: ExternalStr
    body_group: ExternalStr = ""


class MvVirtualNameboxImportFile(ExternalInputModel):
    """MV 虚拟名字框规则导入文件。"""

    rules: list[MvVirtualNameboxRuleSpec] = Field(default_factory=list)
```

Delete now-unused `BaseModel`, `ConfigDict` and `ClassVar` imports from these files.

- [ ] **Step 6: Run rule import tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_plugin_text.py tests/test_event_command_text.py tests/test_nonstandard_data.py
```

Expected: PASS. A bool field accepting `"true"` or `1` is a failure; fix the affected import model so it inherits `ExternalInputModel` and keeps non-convertible fields as strict native types.

- [ ] **Step 7: Run type checking for modified import modules**

Run:

```powershell
uv run basedpyright app/plugin_text app/event_command_text app/plugin_source_text app/note_tag_text app/nonstandard_data app/source_residual app/rmmz/mv_namebox.py tests/test_agent_toolkit_rule_import.py
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 8: Commit Task 3**

Run:

```powershell
git add app/plugin_text/importer.py app/event_command_text/importer.py app/plugin_source_text/models.py app/note_tag_text/importer.py app/nonstandard_data/rules.py app/source_residual/rules.py app/rmmz/mv_namebox.py tests/test_agent_toolkit_rule_import.py
git commit -m "fix: 统一 Agent 规则导入外部类型规范化"
```

Expected: commit succeeds.

### Task 4: Agent Handwritten JSON Boundary Normalization

**Files:**
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Modify: `app/agent_toolkit/services/common.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_feedback.py`
- Test: `tests/test_agent_toolkit_quality_report.py`

- [ ] **Step 1: Add failing tests for handwritten JSON boundaries**

In `tests/test_agent_toolkit_manual_import.py`, add tests near existing manual import validation tests. Use the same fixture style as the file's existing tests:

```python
async def test_manual_translation_import_normalizes_integer_translation_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的整数译文行按外部文本规范化为字符串。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["translation_lines"] = [1]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    assert any(item.translation_lines == ["1"] for item in translated_items)
```

In the same file, add:

```python
async def test_manual_translation_import_rejects_boolean_translation_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的布尔译文行无效。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["translation_lines"] = [True]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert any("bool" in error.message for error in report.errors)
```

In `tests/test_agent_toolkit_feedback.py`, add a focused test for `_read_feedback_texts` if the helper is already imported; otherwise import it from `app.agent_toolkit.services.common`:

```python
async def test_feedback_texts_normalize_integer_entries(tmp_path: Path) -> None:
    """反馈原文清单中的整数按外部文本规范化。"""
    input_path = tmp_path / "feedback.json"
    input_path.write_text(json.dumps(["残留", 123], ensure_ascii=False), encoding="utf-8")

    texts = await _read_feedback_texts(input_path)

    assert texts == ["残留", "123"]
```

Add the boolean rejection test:

```python
async def test_feedback_texts_reject_boolean_entries(tmp_path: Path) -> None:
    """反馈原文清单中的布尔值无效。"""
    input_path = tmp_path / "feedback.json"
    input_path.write_text(json.dumps(["残留", True], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(TypeError) as error_info:
        _ = await _read_feedback_texts(input_path)

    assert "feedback_texts[1]" in str(error_info.value)
    assert "bool" in str(error_info.value)
```

- [ ] **Step 2: Run the new tests and verify they fail before implementation**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_manual_translation_import_normalizes_integer_translation_line tests/test_agent_toolkit_manual_import.py::test_manual_translation_import_rejects_boolean_translation_line tests/test_agent_toolkit_feedback.py::test_feedback_texts_normalize_integer_entries tests/test_agent_toolkit_feedback.py::test_feedback_texts_reject_boolean_entries
```

Expected: normalization tests fail before implementation.

- [ ] **Step 3: Update manual translation import**

In `app/agent_toolkit/services/manual_translation.py`, add imports from common or direct module so the file can use:

```python
from app.external_input import normalize_external_str, normalize_external_str_list
```

Replace the `payload_fact_ids` collection block with:

```python
payload_fact_ids: dict[str, str] = {}
for location_path, raw_entry in payload.items():
    if not isinstance(raw_entry, dict):
        continue
    raw_fact_id = raw_entry.get("fact_id")
    if raw_fact_id is None:
        continue
    fact_id = normalize_external_str(raw_fact_id, f"{location_path}.fact_id").strip()
    if fact_id:
        payload_fact_ids[str(location_path)] = fact_id
```

Replace per-entry fact id reading with:

```python
raw_fact_id = entry.get("fact_id")
fact_id = ""
if raw_fact_id is not None:
    fact_id = normalize_external_str(raw_fact_id, f"{location_path}.fact_id").strip()
```

Replace translation line reading with:

```python
raw_lines_value = entry.get("translation_lines")
if raw_lines_value is None:
    raise TypeError(f"{resolved_location_path}.translation_lines 必须是字符串数组")
translation_lines = normalize_external_str_list(
    raw_lines_value,
    f"{resolved_location_path}.translation_lines",
)
```

- [ ] **Step 4: Update shared handwritten JSON helpers**

In `app/agent_toolkit/services/common.py`, import:

```python
from app.external_input import normalize_external_str_list
```

Update `_read_reset_translation_location_paths`:

```python
raw_paths = payload.get("location_paths")
if raw_paths is None:
    raise TypeError("reset-translations.location_paths 必须是字符串数组")
location_paths = normalize_external_str_list(raw_paths, "reset-translations.location_paths")
```

Update `_read_feedback_texts`:

```python
if isinstance(decoded, list):
    texts = [
        text
        for text in normalize_external_str_list(decoded, "feedback_texts")
        if text.strip()
    ]
elif isinstance(decoded, dict):
    raw_texts = decoded.get("texts")
    if raw_texts is None:
        raise TypeError("反馈原文清单对象必须包含 texts 字符串数组")
    texts = [
        text
        for text in normalize_external_str_list(raw_texts, "feedback_texts.texts")
        if text.strip()
    ]
else:
    raise TypeError("反馈原文清单顶层必须是字符串数组或包含 texts 的对象")
```

- [ ] **Step 5: Run focused agent JSON boundary tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py tests/test_agent_toolkit_quality_report.py
```

Expected: PASS.

- [ ] **Step 6: Run type checking for agent service changes**

Run:

```powershell
uv run basedpyright app/agent_toolkit/services/manual_translation.py app/agent_toolkit/services/common.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add app/agent_toolkit/services/manual_translation.py app/agent_toolkit/services/common.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py
git commit -m "fix: 规范化 Agent 手写 JSON 输入边界"
```

Expected: commit succeeds.

### Task 5: RPG Maker Game Data Normalization

**Files:**
- Modify: `app/rmmz/game_data.py`
- Modify: `app/rmmz/loader.py`
- Create: `tests/test_game_data_external_input.py`

- [ ] **Step 1: Write failing tests for game data models**

Create `tests/test_game_data_external_input.py`:

```python
"""RPG Maker 游戏原文外部输入规范化测试。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.rmmz.game_data import BaseItem, EventCommand
from app.rmmz.loader import collect_missing_map_files_from_map_infos


def test_base_item_normalizes_string_id_and_integer_text() -> None:
    item = BaseItem.model_validate(
        {
            "id": "1",
            "name": 123,
            "note": "",
            "description": "",
        }
    )

    assert item.id == 1
    assert item.name == "123"


def test_base_item_rejects_boolean_id_and_boolean_text() -> None:
    with pytest.raises(ValidationError):
        _ = BaseItem.model_validate(
            {
                "id": True,
                "name": "名前",
                "note": "",
                "description": "",
            }
        )

    with pytest.raises(ValidationError):
        _ = BaseItem.model_validate(
            {
                "id": 1,
                "name": False,
                "note": "",
                "description": "",
            }
        )


def test_event_command_normalizes_string_code() -> None:
    command = EventCommand.model_validate({"code": "401", "parameters": ["こんにちは"]})

    assert command.code == 401


def test_map_infos_accepts_integer_string_id(tmp_path) -> None:
    data_dir = tmp_path
    (data_dir / "MapInfos.json").write_text(
        json.dumps([None, {"id": "1", "name": "Map"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "Map001.json").write_text("{}", encoding="utf-8")

    assert collect_missing_map_files_from_map_infos(data_dir=data_dir) == []


def test_map_infos_rejects_boolean_id(tmp_path) -> None:
    data_dir = tmp_path
    (data_dir / "MapInfos.json").write_text(
        json.dumps([None, {"id": True, "name": "Map"}], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(TypeError) as error_info:
        _ = collect_missing_map_files_from_map_infos(data_dir=data_dir)

    assert "MapInfos.json[1].id" in str(error_info.value)
    assert "bool" in str(error_info.value)
```

- [ ] **Step 2: Run the new game data tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_game_data_external_input.py
```

Expected: tests for integer text and string `MapInfos.json` id fail before implementation.

- [ ] **Step 3: Update `app/rmmz/game_data.py` models**

Modify imports:

```python
from app.external_input import ExternalInputModel, ExternalInt, ExternalStr
from app.rmmz.text_rules import JsonValue
```

Change model bases and fields:

```python
class BaseItem(ExternalInputModel):
    """RPG Maker 数据库基础条目通用模型。"""

    id: ExternalInt
    name: ExternalStr
    note: ExternalStr = ""
    nickname: ExternalStr = ""
    profile: ExternalStr = ""
    description: ExternalStr = ""
    message1: ExternalStr = ""
    message2: ExternalStr = ""
    message3: ExternalStr = ""
    message4: ExternalStr = ""


class EventCommand(ExternalInputModel):
    """RPG Maker 事件指令模型。"""

    code: ExternalInt
    parameters: list[JsonValue]
```

Update remaining models:

```python
class Event(ExternalInputModel):
    """地图事件模型。"""

    id: ExternalInt
    name: ExternalStr
    note: ExternalStr
    pages: list[Page]


class MapData(ExternalInputModel):
    """地图数据模型，对应 `data/MapXXX.json`。"""

    displayName: ExternalStr
    note: ExternalStr
    events: list[Event | None]


class Terms(ExternalInputModel):
    """系统基础词汇模型。"""

    basic: list[ExternalStr]
    commands: list[ExternalStr | None]
    params: list[ExternalStr]
    messages: dict[ExternalStr, ExternalStr]


class System(ExternalInputModel):
    """系统全局配置模型，对应 `data/System.json`。"""

    gameTitle: ExternalStr
    terms: Terms
    elements: list[ExternalStr]
    skillTypes: list[ExternalStr]
    weaponTypes: list[ExternalStr]
    armorTypes: list[ExternalStr]
    equipTypes: list[ExternalStr]


class Troop(ExternalInputModel):
    """敌群战役模型，对应 `data/Troops.json`。"""

    id: ExternalInt
    pages: list[Page]


class CommonEvent(ExternalInputModel):
    """全局公共事件模型，对应 `data/CommonEvents.json`。"""

    id: ExternalInt
    commands: list[EventCommand] = Field(..., alias="list")
```

Keep `Page` inheriting from `ExternalInputModel`:

```python
class Page(ExternalInputModel):
    """事件页模型。"""

    commands: list[EventCommand] = Field(..., alias="list")
```

- [ ] **Step 4: Update `MapInfos.json` id normalization**

In `app/rmmz/loader.py`, import:

```python
from app.external_input import normalize_external_int
```

Replace the id block in `collect_missing_map_files_from_map_infos` with:

```python
raw_id = item.get("id")
try:
    map_id = normalize_external_int(raw_id, f"{MAP_INFOS_FILE_NAME}[{index}].id")
except TypeError as error:
    raise TypeError(str(error)) from error
if map_id <= 0:
    continue
expected_map_names.add(f"Map{map_id:03d}.json")
```

- [ ] **Step 5: Run game data tests**

Run:

```powershell
uv run pytest tests/test_game_data_external_input.py tests/test_text_protocol.py tests/test_rmmz_source_snapshot.py tests/test_rmmz_file_transaction.py
```

Expected: PASS.

- [ ] **Step 6: Run type checking for RMMZ changes**

Run:

```powershell
uv run basedpyright app/rmmz/game_data.py app/rmmz/loader.py tests/test_game_data_external_input.py
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add app/rmmz/game_data.py app/rmmz/loader.py tests/test_game_data_external_input.py
git commit -m "fix: 规范化游戏原文外部类型"
```

Expected: commit succeeds.

### Task 6: Boundary Audit, Full Validation, and Drift Cleanup

**Files:**
- Modify only files identified by the audit commands in this task.
- Test: existing affected tests.

- [ ] **Step 1: Search for remaining external input boundaries**

Run:

```powershell
rg -n "json\\.loads|TypeAdapter|BaseModel|ensure_json_string_list|isinstance\\([^\\n]+, str\\)|isinstance\\([^\\n]+, int\\)|\\bstr\\(|\\bint\\(" app tests
```

Expected: command exits 0 and prints matches. Inspect matches only in external input parsing paths. Internal formatting, SQL row conversion, counters, path rendering and diagnostics are not part of this cleanup.

- [ ] **Step 2: Replace remaining external string-list checks with the shared helper**

For any external JSON boundary still using `ensure_json_string_list`, replace it with:

```python
from app.external_input import normalize_external_str_list

values = normalize_external_str_list(raw_value, "字段名")
```

Keep `ensure_json_string_list` in native output readers or internal JSON helpers when the source is not one of the three external input classes.

- [ ] **Step 3: Replace remaining external integer parsing with the shared helper**

For any external JSON boundary still doing direct `int(value)` or `value.isdecimal()` for a current external integer field, replace it with:

```python
from app.external_input import normalize_external_int

integer_value = normalize_external_int(raw_value, "字段名")
```

Keep business range checks immediately after normalization:

```python
if integer_value < 0:
    raise ValueError("字段名必须是非负整数")
```

- [ ] **Step 4: Run targeted test groups**

Run:

```powershell
uv run pytest tests/test_external_input.py tests/test_translation_line_alignment.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py tests/test_game_data_external_input.py
```

Expected: PASS.

- [ ] **Step 5: Run static type checking**

Run:

```powershell
uv run basedpyright
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 6: Run full pytest**

Run:

```powershell
uv run pytest
```

Expected: PASS.

- [ ] **Step 7: Commit final audit cleanup**

If Step 2 or Step 3 changed files, commit them:

```powershell
git add app tests
git commit -m "chore: 收束剩余外部输入规范化边界"
```

Expected: commit succeeds if there are staged changes. If Step 2 and Step 3 made no changes, do not create an empty commit.

## Self-Review Notes

- Spec coverage: Tasks 1-6 cover the external input module, LLM response, Agent rule import models, Agent handwritten JSON boundaries, RPG Maker game data, `MapInfos.json`, boundary audit, basedpyright and pytest.
- Current-contract wording: The plan uses current field requirements and does not introduce runtime branches named for non-current forms.
- Scope control: Configuration, CLI, environment variables, SQLite schema, native contracts, write-back logic and business rules are explicitly outside the implementation scope.
- Type consistency: The plan defines `ExternalInputModel`, `ExternalStr`, `ExternalInt`, `ExternalStrList`, `normalize_external_str`, `normalize_external_int` and `normalize_external_str_list` in Task 1, then reuses those exact names in later tasks.
