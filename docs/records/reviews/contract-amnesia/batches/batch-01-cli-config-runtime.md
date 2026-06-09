# 批次 01：CLI、配置与运行目录

## 范围

- `app/cli_main.py`
- `app/cli/`
- `app/config/`
- `app/runtime_paths.py`
- `setting.example.toml`
- `tests/test_cli_json_output.py`
- `tests/test_config_overrides.py`
- `tests/test_runtime_paths.py`

## 事实源

- CLI 入口和参数契约事实源：`app/cli_main.py`、`app/cli/parser.py`、`app/cli/arguments.py`、`app/cli/runtime.py`、`app/cli/dispatch.py`、`app/cli/commands/`。
- 配置契约事实源：`app/config/schemas.py`、`app/config/environment.py`、`app/config/overrides.py`、`setting.example.toml`。当前公开环境变量名应是 `ATT_MZ_LLM_BASE_URL` 和 `ATT_MZ_LLM_API_KEY`。
- 运行目录事实源：`app/runtime_paths.py`。当前公开运行目录环境变量名是 `ATT_MZ_HOME`。
- 测试事实源：本批范围内三个测试文件仅应固定当前 CLI、配置、运行目录行为。

## 只读命令

- `rg -n 'legacy|deprecated|fallback|compat|old|schema_version|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本' app/cli_main.py app/cli app/config app/runtime_paths.py setting.example.toml tests/test_cli_json_output.py tests/test_config_overrides.py tests/test_runtime_paths.py`
  - 结果：命中 `app/config/environment.py` 对旧模型环境变量前缀的枚举和用户可见报错；命中 `tests/test_config_overrides.py`、`tests/test_cli_json_output.py` 中多处旧配置、旧 CLI、旧输出模式描述；`app/cli_main.py` 仅命中第三方兼容性警告过滤。
- `rg -n 'raise|ValueError|RuntimeError|error|错误|失败|无法|请|旧|兼容|回退|废弃' app/cli_main.py app/cli app/config app/runtime_paths.py tests/test_cli_json_output.py tests/test_config_overrides.py`
  - 结果：确认 `app/config/environment.py` 在配置加载路径中显式拒绝旧环境变量并输出旧名称；确认测试断言旧字段、旧环境变量和旧输出参数相关报错。
- `rg -n -C 4 'legacy|system_prompt_file|ATT_MZ_LLM|RPG_MAKER_TOOLS|旧模型|旧的单提示词|已废弃|保留旧 CLI' app/config tests/test_config_overrides.py setting.example.toml`
  - 结果：用于确认旧环境变量运行路径和旧提示词字段测试上下文。
- `rg -n -C 4 'output-mode|json-output|agent-output|旧输出模式|已删除|removed|旧' app/cli app/cli_main.py tests/test_cli_json_output.py`
  - 结果：当前 CLI 代码未发现专门识别旧输出参数；测试命名和说明保留旧输出模式语义。
- `rg -n 'system_prompt_file|RPG_MAKER_TOOLS|LEGACY|legacy|deprecated|废弃|旧' app/config app/cli app/cli_main.py app/runtime_paths.py setting.example.toml tests/test_config_overrides.py tests/test_cli_json_output.py tests/test_runtime_paths.py`
  - 结果：收束旧字段、旧环境变量和旧输出模式命中范围。
- `rg -n 'data|logs|outputs|tmp|dist|target|venv|pytest_cache|__pycache__|ATT_MZ_HOME|runtime|目录|根目录|workspace|setting' app/runtime_paths.py tests/test_runtime_paths.py app/config setting.example.toml`
  - 结果：运行目录相关命中未发现历史契约分支。
- `$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-01-cli-config-runtime.md' -Pattern $patterns`
  - 结果：无输出，四个自检模式均未命中。

## 结论

FAIL

## 发现

### P0：旧模型环境变量在当前配置加载路径被显式识别并展示

- 证据：`app/config/environment.py:10`
- 证据：`app/config/environment.py:39`
- 证据：`app/config/environment.py:74`
- 证据：`app/config/environment.py:95`
- 违反准则：运行时失忆化
- 影响范围：`load_environment_overrides()` 每次加载模型连接环境变量时都会先枚举 `RPG_MAKER_TOOLS_` 旧前缀，并在用户可见错误中展示“旧模型环境变量”和具体旧名称。这让当前配置入口具备识别、拒绝和解释历史形态的运行时分支。
- 建议收束：删除 `_LEGACY_ENV_PREFIX`、`_collect_legacy_environment_names()`、`_legacy_env_name()`、`_format_legacy_environment_error()` 以及 `load_environment_overrides()` 中的旧前缀检查；只读取当前 `ATT_MZ_LLM_BASE_URL`、`ATT_MZ_LLM_API_KEY`，缺失或无效时只说明当前必需配置。
- 后续验证：运行 `rg -n 'legacy|RPG_MAKER_TOOLS|旧模型环境变量|旧前缀|已停用' app/config tests/test_config_overrides.py`，再运行 `uv run basedpyright` 和 `uv run pytest tests/test_config_overrides.py`。

### P2：配置测试固定旧字段和旧环境变量模型

- 证据：`tests/test_config_overrides.py:460`
- 证据：`tests/test_config_overrides.py:464`
- 证据：`tests/test_config_overrides.py:486`
- 证据：`tests/test_config_overrides.py:495`
- 证据：`tests/test_config_overrides.py:582`
- 证据：`tests/test_config_overrides.py:590`
- 违反准则：测试失忆化
- 影响范围：测试用例名称、说明、输入和断言继续表达“旧的单提示词配置”“已废弃”“legacy 环境变量”等历史模型，后续修改容易被测试要求继续保留历史识别和历史错误文案。
- 建议收束：把旧字段用例改为当前契约下的普通未知字段拒绝测试，断言 Pydantic 严格配置模型或配置加载统一错误；删除旧环境变量专用测试，改为只覆盖当前环境变量覆盖成功和当前必需配置缺失/非法。
- 后续验证：运行 `rg -n 'legacy|RPG_MAKER_TOOLS|system_prompt_file|旧|废弃|已停用' tests/test_config_overrides.py`，再运行 `uv run pytest tests/test_config_overrides.py`。

### P2：CLI JSON 测试把未知参数解释为旧输出模式

- 证据：`tests/test_cli_json_output.py:821`
- 证据：`tests/test_cli_json_output.py:824`
- 证据：`tests/test_cli_json_output.py:825`
- 证据：`tests/test_cli_json_output.py:839`
- 违反准则：测试失忆化
- 影响范围：当前 CLI 入口对 `--json`、`--agent-mode` 的表现只是通用参数错误，但测试名称和说明把它描述成“旧输出模式参数已删除”，让测试模型保留历史输出模式概念。
- 建议收束：重命名测试为“未知全局/子命令参数返回 JSON 参数错误”，用无历史含义的参数名验证通用错误路径；若仍需覆盖 `--json`、`--agent-mode`，只作为普通未知参数样例，不在名称、注释和断言说明历史。
- 后续验证：运行 `rg -n '旧输出模式|--json|--agent-mode|已删除|removed_output' tests/test_cli_json_output.py app/cli app/cli_main.py`，再运行 `uv run pytest tests/test_cli_json_output.py`。

### P2：自定义提示词测试用历史 CLI 解释当前行为

- 证据：`tests/test_config_overrides.py:419`
- 证据：`tests/test_config_overrides.py:423`
- 证据：`app/cli/parser.py:696`
- 违反准则：测试失忆化
- 影响范围：CLI 帮助把“自定义系统提示词缺少输出协议模板时自动追加本轮输出协议”作为当前行为描述，测试说明却写成“保留旧 CLI 用法”，会把当前行为的业务意图绑定到历史兼容叙事。
- 建议收束：保留或调整当前行为时，用当前契约描述测试，例如“自定义提示词缺少模板时追加当前输出协议”；删除“旧 CLI”表述，并确认实现层没有为历史输入保留专用分支。
- 后续验证：运行 `rg -n '保留旧 CLI|旧 CLI|fallback|回退|兼容' tests/test_config_overrides.py app/cli app/config`，再运行 `uv run pytest tests/test_config_overrides.py`。

## 交叉引用

- 提示词模板加载和最终 prompt 组装实现不在本批范围；若相邻批次覆盖相关模块，建议确认“自动追加本轮输出协议”只作为当前契约行为存在，没有历史输入识别分支或历史错误文案。
- 配置加载入口若由其他批次覆盖，应同步删除旧环境变量检查对应测试，避免运行时代码和测试事实源互相保留历史模型。

## 已查无发现范围

- `setting.example.toml` 当前示例使用 `[text_translation.system_prompt_files]`、`ATT_MZ_HOME` 相关运行目录未出现旧配置说明。
- `app/runtime_paths.py` 和 `tests/test_runtime_paths.py` 未发现旧目录、迁移目录或历史运行目录分支；`.venv` 命中用于识别开发态路径，不属于本专项确认问题。
- `app/cli_main.py` 的 `compat` 命中来自第三方 Pydantic 兼容性警告过滤，未发现 A.T.T MZ 历史 CLI/JSON 契约分支。
- `app/cli/commands/`、`app/cli/reports.py`、`app/cli/arguments.py` 本批关键字扫描未确认历史形态识别或历史文案问题。
