# 批次 02：SQLite schema 与 persistence

## 范围

- `app/persistence/`
- `app/persistence/schema/current.sql`
- `rust/src/native_core/scope_index/storage.rs`
- `rust/src/native_core/write_back_plan/repository.rs`
- `tests/test_persistence.py`

## 事实源

- SQLite 当前 DDL 事实源是 `app/persistence/schema/current.sql`，声明当前 schema 为 v17，并由 Python persistence 与 Rust native storage 共享。
- Python persistence 侧当前 schema 常量与 SQL 语句集中在 `app/persistence/sql.py`，打开已有数据库时由 `app/persistence/repository.py` 做表集合、表结构和 `schema_version` 校验。
- Text Fact 持久化会话能力在 `app/persistence/text_fact_records.py`，译文主表读写在 `app/persistence/translation_records.py`，运行记录与质量错误读写在 `app/persistence/run_records.py`。
- Rust 侧索引写库路径在 `rust/src/native_core/scope_index/storage.rs`，写回计划读取译文与 text fact scope 的路径在 `rust/src/native_core/write_back_plan/repository.rs`。
- `tests/test_persistence.py` 固定 Python persistence 可观察契约，`rust/src/native_core/scope_index/storage.rs` 内部测试固定 Rust 写库行为。

## 只读命令

- `rg -n 'schema_version|legacy|deprecated|fallback|compat|old|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期' app/persistence rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs tests/test_persistence.py`
- `Get-Content -Raw -LiteralPath 'app\persistence\schema\current.sql'`
- `rg -n 'CURRENT_SCHEMA_VERSION|TEXT_FACT_SCHEMA_VERSION|schema_version|text_facts_v2|text_fact_scope_v2|translation_items' app/persistence rust/src/native_core`
- `rg --files app/persistence`
- `rg -n -C 3 'legacy|旧库|旧版|迁移|兼容|deprecated|fallback|old|历史|回退|旧格式|当前版本|schema_version|v2' app/persistence tests/test_persistence.py`
- `rg -n -C 3 'legacy|旧库|旧版|迁移|兼容|deprecated|fallback|old|历史|回退|旧格式|当前版本|schema_version|v2' rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs`
- `rg -n -C 12 '_schema_mismatch_error|ensure_schema_compatible|list_games_with_issues|resolve_registered_title_by_path|open_game|schema_version' app/persistence/repository.py`
- `rg -n -C 10 '旧|legacy|old|迁移|v2|schema version|schema_version|旧索引|当前数据库' app/persistence/text_fact_records.py app/persistence/text_index_records.py app/persistence/source_snapshot_records.py app/persistence/translation_records.py`
- `rg -n -C 12 'validate_schema_version|mismatch|unreadable|旧|迁移|schema_version|replaces_old|old|v2' rust/src/native_core/scope_index/storage.rs`
- `rg -n -C 12 'read_current_text_fact_scope_key|unresolved|不再匹配|schema version|schema_version|旧|迁移|v2' rust/src/native_core/write_back_plan/repository.rs`
- `rg -n -C 12 'legacy|旧库|旧版|old-game|AAA旧库|旧索引|当前版本|schema_version|v2 fact identity' tests/test_persistence.py`
- `rg -n 'text_facts_v2|text_fact_scope_v2|text_fact_render_parts_v2|text_fact_domain_payloads_v2|TextFactV2|TextFactScopeV2|TEXT_FACT_SCHEMA_VERSION|v2 fact|v2 文本事实|text fact v2' app/persistence tests/test_persistence.py`
- `rg -n 'text_facts_v2|text_fact_scope_v2|text_fact_render_parts_v2|text_fact_domain_payloads_v2|TEXT_FACT_SCHEMA_VERSION|v2 fact|v2 文本事实|text fact v2|replaces_old|旧 fact|旧标题|snapshot-v1|snapshot-v2|rules-v1|rules-v2' rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs`
- `rg -n '旧记录|旧索引|旧 v2|旧库|旧版|legacy|old-game|replaces_old|迁移数据库|迁移|v1|v2' app/persistence rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs tests/test_persistence.py`
- `$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-02-sqlite-persistence.md' -Pattern $patterns`
- 报告自检结果：`Select-String` 无输出，指定残留文本 0 命中。

## 结论

FAIL

## 发现

### P0：当前 SQLite 与运行时仍以 Text Fact v2 作为正式契约名

- 证据：`app/persistence/schema/current.sql:382`
- 证据：`app/persistence/schema/current.sql:424`
- 证据：`app/persistence/sql.py:41`
- 证据：`app/persistence/sql.py:50`
- 证据：`app/persistence/text_fact_records.py:120`
- 证据：`app/persistence/text_fact_records.py:128`
- 证据：`app/persistence/translation_records.py:251`
- 证据：`rust/src/native_core/write_back_plan/repository.rs:401`
- 证据：`rust/src/native_core/write_back_plan/repository.rs:422`
- 证据：`rust/src/native_core/scope_index/storage.rs:826`
- 违反准则：运行时失忆化 | schema 失忆化 | 文案失忆化
- 影响范围：当前 DDL、Python 常量、Python 会话 API、Rust SQL、Rust/Python 错误文案和测试都把 `text_facts_v2`、`text_fact_scope_v2`、`TEXT_FACT_SCHEMA_VERSION = 2`、`v2 fact identity` 当成当前事实源。当前执行路径不仅依赖版本化表名，还会向用户展示 `text fact v2 scope`、`当前 v2 文本事实` 等版本记忆。
- 建议收束：将正式 schema/API/错误文案统一改为无版本当前名，例如 `text_facts`、`text_fact_scope`、`TextFactRecord`、`文本事实身份`；如果内部仍需 schema 版本校验，限制在 `schema_version` 当前结构校验中，不进入表名、函数名、用户文案和 JSON 可见字段。同步更新 Python SQL 常量、Rust SQL、tests 对当前表名和错误文案的断言。
- 后续验证：清理后运行 `rg -n 'text_facts_v2|text_fact_scope_v2|TextFactV2|TextFactScopeV2|TEXT_FACT_SCHEMA_VERSION|v2 fact|v2 文本事实|text fact v2' app/persistence rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs tests/test_persistence.py`，再执行 `uv run basedpyright`、`uv run pytest` 和 Rust 相关 `cargo fmt -- --check`、`cargo clippy --all-targets -- -D warnings`、`cargo test`。

### P0：Rust schema 校验错误把历史迁移作为当前用户动作

- 证据：`rust/src/native_core/scope_index/storage.rs:278`
- 证据：`rust/src/native_core/scope_index/storage.rs:286`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：`rebuild-text-index` 的 Rust storage 校验在 `schema_version` 不可读或不匹配时提示“请使用当前版本重新注册或迁移数据库”。这让当前运行时文案把“迁移数据库”作为用户需要理解和选择的当前动作，而不是只说明当前结构要求、当前问题和可执行修正方式。
- 建议收束：删除“迁移数据库”表述，和 Python `_schema_mismatch_error` 的当前失效语义对齐；只提示数据库结构不符合当前要求，以及重新注册、重新导入规则和重建文本索引等当前流程动作。
- 后续验证：清理后运行 `rg -n '迁移|旧版|legacy|compat|fallback' rust/src/native_core/scope_index/storage.rs app/persistence tests/test_persistence.py`，并覆盖 schema mismatch 的 Rust/Python 错误文案测试。

### P2：测试与内部测试夹具保留 legacy/old/旧库模型

- 证据：`tests/test_persistence.py:368`
- 证据：`tests/test_persistence.py:375`
- 证据：`tests/test_persistence.py:831`
- 证据：`tests/test_persistence.py:835`
- 证据：`tests/test_persistence.py:855`
- 证据：`tests/test_persistence.py:859`
- 证据：`rust/src/native_core/scope_index/storage.rs:1528`
- 证据：`rust/src/native_core/scope_index/storage.rs:1560`
- 证据：`rust/src/native_core/scope_index/storage.rs:1566`
- 违反准则：测试失忆化
- 影响范围：Python persistence 测试用 `create_legacy_registry_database`、`legacy_schema_database`、`旧库`、`old-game` 表达“缺少当前表的无效数据库”；Rust 内部测试用 `replaces_old_text_fact_v2_scope_atomically`、`旧标题`、`旧 fact` 表达同一当前替换行为。测试模型会继续把历史形态当成开发者需要理解的概念，并反向固化源码命名。
- 建议收束：将这些测试改名为 current-invalid/incomplete/outdated-shape 一类当前无效输入模型；测试数据使用中性名称，例如 `InvalidSchema.db`、`unrelated-game`、`previous-title` 或当前替换语义，不再使用 legacy/old/旧库/旧版/旧 fact。行为断言保留“无关无效数据库不影响路径解析”“当前 scope 原子替换”。
- 后续验证：清理后运行 `rg -n 'legacy|old-game|旧库|旧版|旧 fact|旧标题|replaces_old' tests/test_persistence.py rust/src/native_core/scope_index/storage.rs`，并运行对应 persistence pytest 与 Rust storage 单测。

## 交叉引用

- 该批发现与 Text Fact 当前契约命名、CLI/JSON 输出、Rust write-back 文案和测试命名有关；建议与负责 CLI 用户文案、Rust native text facts、写回计划和测试总线的批次合并收束，避免只改 SQLite DDL 而留下 API、错误文案或测试模型漂移。
- `schema_version` 当前结构校验本身没有确认发现；问题集中在版本化表名/API/文案和“迁移数据库”用户动作。

## 已查无发现范围

- `app/persistence/repository.py` 打开已有数据库时按表集合、表结构签名和 `schema_version` 显式失败，未发现自动补建缺失表、静默迁就或按旧 schema 分支处理。
- `app/persistence/schema/current.sql` 未发现迁移脚本、兼容分支或旧表自动映射逻辑；确认发现来自当前 DDL 仍使用版本化 text fact 名称。
- `rust/src/native_core/write_back_plan/repository.rs` 读取译文时通过当前 text fact 身份与 hash 关联，未发现按旧 location-only 译文身份回退写回；确认发现来自版本化表名和用户文案。
- `app/persistence/source_snapshot_records.py`、`app/persistence/text_index_records.py` 中“替换旧记录/旧索引”描述按上下文更接近“替换上一轮当前数据”，本批未单独计为确认缺陷，但建议在 P0/P2 收束时一并改成“替换现有记录/现有索引”以降低误读。
