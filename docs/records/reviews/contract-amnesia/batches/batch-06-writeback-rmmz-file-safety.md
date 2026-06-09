# 批次 06：写回、RMMZ 与文件安全

## 范围

- `app/application/`
- `app/rmmz/`
- `app/native_write_plan.py`
- `rust/src/native_core/write_back_plan/`
- `tests/test_rmmz_*.py`
- `tests/test_write_back_transactions.py`
- `tests/test_font_replacement_transactions.py`

本批只做只读取证和本报告写入；未执行会改变游戏、数据库、运行数据或源码状态的命令。

## 事实源

- 当前文件视图只有翻译来源和当前运行两类：`app/rmmz/game_file_view.py:6`、`app/rmmz/game_file_view.py:9`、`app/rmmz/game_file_view.py:10`。
- 干净游戏注册会创建可信源快照，并校验 `data_origin`、`plugins_origin.js` 和 `plugins_source_origin`：`app/rmmz/source_snapshot.py:23`、`app/rmmz/source_snapshot.py:30`、`app/rmmz/source_snapshot.py:34`、`app/rmmz/source_snapshot.py:36`、`app/rmmz/source_snapshot.py:40`。
- 写回前当前主路径会读取并校验可信源快照 manifest：`app/application/handler.py:1404`、`app/application/handler.py:1406`、`app/application/handler.py:1407`。
- 显式翻译源视图要求原始备份存在：`app/rmmz/loader.py:73`、`app/rmmz/loader.py:84`、`app/rmmz/loader.py:85`；`load_translation_source_game_data` 同样要求原始备份：`app/rmmz/loader.py:126`、`app/rmmz/loader.py:137`。
- `origin`、`source_snapshot`、`ACTIVE_RUNTIME`、`stale` 在本批多数命中表达当前可信源、当前运行视图、当前失效检查，不按历史形态直接定性。

## 只读命令

1. 指定检索命令：

```powershell
rg -n 'write|write-back|snapshot|origin|backup|fallback|compat|legacy|old|stale|load_game_data|require_origin|current runtime|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期|当前运行' app/application app/rmmz app/native_write_plan.py rust/src/native_core/write_back_plan tests/test_rmmz_*.py tests/test_write_back_transactions.py tests/test_font_replacement_transactions.py
```

结果：PowerShell 下 `tests/test_rmmz_*.py` 作为路径参数传给 `rg` 时触发 Windows 路径语法错误 `os error 123`，其余路径仍输出命中。随后用等价安全展开覆盖同一文件集合：

```powershell
$rmmzTests = Get-ChildItem -LiteralPath 'tests' -Filter 'test_rmmz_*.py' -File | ForEach-Object { $_.FullName }
rg -n 'write|write-back|snapshot|origin|backup|fallback|compat|legacy|old|stale|load_game_data|require_origin|current runtime|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期|当前运行' app/application app/rmmz app/native_write_plan.py rust/src/native_core/write_back_plan $rmmzTests tests/test_write_back_transactions.py tests/test_font_replacement_transactions.py
```

结果：退出码 0；主要命中集中在可信源快照、写回、字体替换、过期规则、当前运行审计，以及本报告列出的确认问题。

2. 指定检索命令：

```powershell
rg -n 'load_game_data|GameFileView|source_snapshot|origin_backups|require_origin_backups|TRANSLATION_SOURCE|ACTIVE_RUNTIME' app/rmmz app/application tests
```

结果：退出码 0；确认 `app/rmmz/loader.py` 同时存在显式视图入口和兼容完整加载入口，且 `tests` 中仍有大量 `load_game_data` 调用。非本批测试文件仅作交叉引用，不作为本批确认发现逐项展开。

3. 报告自检命令：

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-06-writeback-rmmz-file-safety.md' -Pattern $patterns
```

结果：无命中。

补充定位命令均为只读 `rg`、`Get-Content` 和 `Test-Path`，用于核实行号、导出面和上下文；未读取禁止目录。

## 结论

FAIL

## 发现

### P0：兼容完整加载入口仍在缺可信源快照时回退当前运行文件

- 证据：`app/rmmz/loader.py:62`、`app/rmmz/loader.py:66`、`app/rmmz/loader.py:451`、`app/rmmz/loader.py:454`、`app/rmmz/loader.py:468`、`app/rmmz/loader.py:471`、`app/rmmz/loader.py:570`、`app/rmmz/loader.py:572`、`app/rmmz/__init__.py:9`、`app/rmmz/__init__.py:24`
- 违反准则：运行时失忆化
- 影响范围：`load_game_data()` 标注为“兼容完整游戏数据”，并以 `require_origin_backups=False` 调用内部加载逻辑。缺少 `data_origin`、`plugins_origin.js` 或 `plugins_source_origin` 时，解析函数会读取当前运行文件；同时该入口仍从 `app.rmmz` 公共导出。当前契约已经区分“翻译来源文件”和“当前运行文件”，且写回主路径要求可信源快照 manifest，这个兼容入口会让调用者在缺少可信源快照时继续按当前运行文件构造翻译源数据。
- 建议收束：删除 `load_game_data()` 的兼容语义，或改成当前契约下的显式入口别名并强制可信源快照；同步替换本批和跨批测试里的默认调用为 `load_translation_source_game_data()`、`load_active_runtime_game_data()` 或 `load_game_data_for_view(...)`。若公共导出不再是当前契约，移出 `app/rmmz/__init__.py`。
- 后续验证：清理后运行 `rg -n 'load_game_data\(|兼容完整|require_origin_backups=False|return layout.plugins_path|return await _read_direct_plugin_source_files\(layout.js_dir / "plugins"\)' app/application app/rmmz tests`，并执行覆盖 RMMZ 读写契约的针对性测试，例如 `uv run pytest tests/test_rmmz_source_snapshot.py tests/test_rmmz_file_transaction.py tests/test_rmmz_post_write_audit.py`。

### P2：应用层包级导出保留历史适配表述

- 证据：`app/application/__init__.py:21`、`app/application/__init__.py:22`
- 违反准则：运行时失忆化
- 影响范围：`__getattr__` 通过 `_HANDLER_EXPORTS` 动态返回 handler 对象，docstring 直接写“历史包级导出”。这会把旧导入面作为当前包初始化逻辑的一部分保留下来，属于 adapter 层残留历史模型。
- 建议收束：若这些包级导出仍是当前契约，改名和注释为当前懒加载导出；若只是旧导入面，删除 `_HANDLER_EXPORTS` 和 `__getattr__`，同步修正内部调用点。
- 后续验证：运行 `rg -n '历史包级导出|_HANDLER_EXPORTS|from app.application import' app tests`，确认没有历史导出表述或旧导入面依赖。

### P2：空规则导入 helper 仍保留旧调用点参数

- 证据：`app/application/flow_gate.py:269`、`app/application/flow_gate.py:273`、`app/application/flow_gate.py:276`
- 违反准则：运行时失忆化
- 影响范围：`ensure_empty_rule_import_allowed` 保留 `candidate_count` 参数，并在 docstring 中说明“仅保留给旧调用点传入报告上下文”，函数体用 `_ = candidate_count` 丢弃。当前运行时代码仍为旧调用点维持签名，容易让调用者继续传递已经不参与当前契约的候选数量。
- 建议收束：移除 `candidate_count` 参数和相关调用；若报告上下文仍需要候选数量，应在当前报告模型中显式建模，而不是由空规则确认 helper 保留旧参数。
- 后续验证：运行 `rg -n 'candidate_count=.*ensure_empty_rule_import_allowed|ensure_empty_rule_import_allowed\(|旧调用点' app tests`，确认调用面和注释已经收束到当前契约。

### P2：Rust 写回计划测试用 `legacy` 表达非法 mode

- 证据：`rust/src/native_core/write_back_plan/test_support.rs:1523`
- 违反准则：测试失忆化
- 影响范围：测试用例本意是校验非法 `mode` 在进入热路径前失败，但输入值选择了 `legacy`。生产代码没有专门兼容该值，属于测试层历史词汇残留；同时错误文案会回显非法值，未来排障时容易误以为存在过 `legacy` 模式。
- 建议收束：把测试输入改为中性非法值，例如 `invalid_mode`，保持断言聚焦“非当前枚举值会失败”。
- 后续验证：运行 `rg -n 'legacy' rust/src/native_core/write_back_plan tests`，并执行 Rust 写回计划相关单测。

## 交叉引用

- 指定命令 2 显示 `tests/` 中非本批文件也大量调用 `load_game_data`，这会放大 P0 入口的影响。因本批范围只允许确认指定测试文件，建议其他批次统一检查测试模型是否仍依赖兼容加载入口。
- `old_font`、`source_font_names`、`origin_font_reference` 属于字体替换当前业务语义，不按历史形态计入。
- `stale_plugin_rules`、`source_snapshot_changed`、`validate_source_snapshot_manifest` 表达当前失效检查和可信源校验，不按历史形态计入。

## 已查无发现范围

- `app/native_write_plan.py` 的 Python/Rust JSON 解析和报告字段校验未发现历史字段兼容分支。
- `rust/src/native_core/write_back_plan/` 生产代码的 `WritePlanMode` 当前只接受 `write_back`、`rebuild_active_runtime`、`write_terminology`、`quality_gate`，未发现专门识别历史 mode 的生产分支。
- `app/application/file_writer.py` 的事务备份、回滚目录和临时替换逻辑属于当前文件安全机制，未发现历史形态分支。
- RMMZ MV/MZ 写回路径、当前运行审计、可信源 manifest 校验命中较多，但除上述问题外未确认污染当前事实源的历史表述。
