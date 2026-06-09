# 批次 07：Rust native 与 Python adapter 边界

## 范围

- `rust/src/`
- `app/native_contract.py`
- `app/native_*.py`
- `tests/test_native_*.py`
- `rust/src/native_core.rs`

第二条强制检索额外覆盖 `app/agent_toolkit`、`app/application`、`tests`，本报告仅把范围内文件作为确认发现来源，范围外命中只放入交叉引用。

## 事实源

- Rust/Python native 契约版本检查：`app/native_contract.py`
- Python native 适配层：`app/native_*.py`
- Rust native 核心与存储边界：`rust/src/`
- Native 边界测试：`tests/test_native_adapters.py`、`tests/test_native_scope_index.py`

## 只读命令

- 原命令 1：
  `rg -n 'schema_version|legacy|fallback|old|same shape|旧报告|native|adapter|contract|unsupported|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' rust/src app/native_contract.py app/native_*.py tests/test_native_*.py`
  - 结果：失败。PowerShell 未展开传给 `rg` 的通配符路径，报 `app/native_*.py`、`tests/test_native_*.py` Windows 路径错误 `os error 123`。
- 等价补跑 1：
  `$paths = @('rust/src', 'app/native_contract.py') + (Get-ChildItem -Path 'app/native_*.py' -File | ForEach-Object { $_.FullName }) + (Get-ChildItem -Path 'tests/test_native_*.py' -File | ForEach-Object { $_.FullName }); rg -n 'schema_version|legacy|fallback|old|same shape|旧报告|native|adapter|contract|unsupported|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' -- $paths`
  - 结果：成功，命中 native 契约版本、adapter 旧报告同形说明、Rust schema mismatch 文案、native 测试旧模型等候选。
- 原命令 2：
  `rg -n '调用 native|返回旧报告同形|fallback|TextScope|build\(|Python 完整|Rust|adapter|schema_version' app/native_*.py app/agent_toolkit app/application tests`
  - 结果：失败。PowerShell 未展开 `app/native_*.py`，报 Windows 路径错误 `os error 123`。
- 等价补跑 2：
  `$paths = (Get-ChildItem -Path 'app/native_*.py' -File | ForEach-Object { $_.FullName }) + @('app/agent_toolkit', 'app/application', 'tests'); rg -n '调用 native|返回旧报告同形|fallback|TextScope|build\(|Python 完整|Rust|adapter|schema_version' -- $paths`
  - 结果：成功，命中 native 适配层、应用层禁止 Python 完整文本范围回退的 guard、扫描预算测试等。
- 辅助取证命令：
  - `rg -n '版本过旧|旧报告同形|旧 Rust|旧版|旧契约|legacy|old|stale|schema_version|不受支持|缺少 .*入口|回退|迁移|兼容|废弃|历史' -- <展开后的 app/native_*.py>`
  - `rg -n 'legacy|旧版|旧格式|历史|兼容|迁移|废弃|回退|unsupported|不受支持|版本过旧|旧报告|旧范围服务|旧 Rust|v1 schema|old text fact|old_text|old_scope|old_text_fact' -- rust/src`
  - `rg -n 'old|legacy|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|same shape|旧报告|版本过旧|不受支持|unsupported|schema_version|stale|v[0-9]+' -- tests/test_native_adapters.py tests/test_native_scope_index.py`
  - `Get-Content -LiteralPath <范围内文件>` 与行号切片命令，用于确认下列证据行。

## 结论

FAIL

统计：P0=2，P1=0，P2=2，P3=0。

## 发现

### P0：native 契约版本错误把当前失败描述成旧扩展

- 证据：`app/native_contract.py:6`
- 证据：`app/native_contract.py:11`
- 证据：`app/native_contract.py:15`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：`ensure_native_contract_version` 会读取 `native_contract_version`，对缺失或低于当前常量的扩展抛出 `Rust 原生扩展版本过旧`。这让当前运行时和用户错误文案继续识别“旧扩展”形态，而不是只表达“当前 Rust/Python 契约不满足”。
- 建议收束：将 `_STALE_NATIVE_ERROR_MESSAGE`、测试名和用户文案改为当前契约失败描述，例如“Rust 原生扩展不满足当前 Python 契约，请重新构建原生扩展”。保留必要版本校验时，只把低版本视为当前契约无效，不再使用 stale/旧版/过旧语义。
- 后续验证：`rg -n '版本过旧|stale_native_contract|旧版 Rust|旧契约|旧 Rust|legacy' app/native_*.py tests/test_native_*.py`；再运行 `uv run pytest tests/test_native_adapters.py`。

### P0：Rust storage schema mismatch 文案把迁移放进当前运行时输出

- 证据：`rust/src/native_core/scope_index/storage.rs:278`
- 证据：`rust/src/native_core/scope_index/storage.rs:286`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：`rebuild-text-index` 读取数据库 schema 失败或版本不符时，当前运行时错误文案要求用户“重新注册或迁移数据库”。“迁移”属于历史处理语境，按失忆化边界应留在迁移指南或发布说明中，当前运行时只说明当前数据库不满足要求和可执行下一步。
- 建议收束：删除运行时错误里的“迁移数据库”，改为“请使用当前版本重新注册游戏或重建数据库后运行 rebuild-text-index”。如确需迁移说明，放入迁移指南并从错误文案指向当前可执行动作。
- 后续验证：`rg -n '迁移数据库|迁移' rust/src app/native_*.py`；针对 storage mismatch 运行现有 native storage 测试。

### P2：native 候选 adapter 注释仍以旧报告形状定义当前输出

- 证据：`app/native_placeholder_scan.py:28`
- 证据：`app/native_structured_placeholder_scan.py:28`
- 证据：`app/native_note_tag_scan.py:74`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：三个 adapter 的公共 helper docstring 都写“返回旧报告同形明细”。即使代码当前只是在归一化 Rust 候选结果，这些注释仍把当前输出契约锚定在旧报告模型上，会影响后续维护者判断哪些字段是当前事实源。
- 建议收束：把 docstring 改为“返回当前报告候选明细”或“返回规则候选明细”，并把当前报告字段定义集中到当前 adapter/报告 schema；不要用旧报告形状解释现行输出。
- 后续验证：`rg -n '旧报告同形|same shape|旧报告' app/native_*.py tests/test_native_*.py`。

### P2：native 边界测试继续用旧版、legacy、旧路径命名当前契约失败

- 证据：`tests/test_native_adapters.py:255`
- 证据：`tests/test_native_adapters.py:293`
- 证据：`tests/test_native_adapters.py:906`
- 证据：`tests/test_native_adapters.py:932`
- 证据：`tests/test_native_adapters.py:968`
- 证据：`tests/test_native_adapters.py:1175`
- 证据：`tests/test_native_scope_index.py:579`
- 违反准则：测试失忆化
- 影响范围：测试类、测试函数和断言文案使用“旧版 Rust 扩展”“stale native contract”“legacy-v1-fingerprint”“旧 text fact schema”“旧 Python runtime scanner”“旧范围服务”等历史模型来表达当前失败路径。测试作为事实源会继续驱动实现保留历史概念，尤其会固化 P0 中的“版本过旧”用户文案。
- 建议收束：将测试对象改名为“缺少当前契约字段”“契约版本不满足当前要求”“schema 指纹不一致”“禁止临时 runtime scan”等当前状态；测试 payload 中的 `legacy-*`、`old_*` 仅在确有历史记录需要时移入 docs/records，不作为当前单测模型。
- 后续验证：`rg -n '旧版|旧 Rust|旧契约|旧范围服务|旧 Python|legacy|stale_.*contract|版本过旧' tests/test_native_*.py`；再运行 `uv run pytest tests/test_native_adapters.py tests/test_native_scope_index.py`。

## 交叉引用

- 强制命令 2 命中 `app/application/flow_gate.py:91`、`app/application/write_back_gate.py:67` 的“不能回退构建 Python 完整文本范围”运行时 guard。它们在本批范围外，且语义更偏应用层写回/翻译 gate，建议由对应应用层批次复核是否需要把“回退/Python 完整”改成当前事实源描述。
- 强制命令 2 命中 `tests/scan_budget.py:362` 之后的批次 7 guard，属于扫描预算测试事实源；本批未把它列为确认发现，但它与本批 P2 测试失忆化方向一致，可由测试契约批次统一清理命名。

## 已查无发现范围

- `rust/src/native_core.rs` 中的 `old gate`、`旧`、`旧文本` 是测试正文样例；`old_font_names` 是字体替换业务输入“待替换字体名”，不是历史契约。
- `app/native_quality.py` 的 `old_font_names` 同属当前字体替换输入，不按旧契约处理。
- `stale_rule_details`、`stale_rule_count`、`stale` 译文身份检查表示当前事实新鲜度/过期状态；未发现生产路径按旧格式回退处理。
- `text_facts_v2`、`schema_version`、`text_fact_schema_version` 是当前持久化与 Rust/Python 边界契约名；仅在与“旧/legacy/迁移/版本过旧”语义绑定时列为发现。
