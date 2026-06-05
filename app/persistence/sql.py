"""多游戏数据库管理器使用的 SQL 语句模块。"""

TRANSLATION_TABLE_NAME = "translation_items"
METADATA_TABLE_NAME = "metadata"
LANGUAGE_SETTINGS_TABLE_NAME = "language_settings"
SCHEMA_VERSION_TABLE_NAME = "schema_version"
PLUGIN_TEXT_RULES_TABLE_NAME = "plugin_text_rules"
PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME = "plugin_source_text_rules"
NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME = "nonstandard_data_text_rules"
PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME = "plugin_source_runtime_write_map"
PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME = "plugin_source_runtime_scan_cache"
SOURCE_SNAPSHOT_FILES_TABLE_NAME = "source_snapshot_files"
NOTE_TAG_TEXT_RULES_TABLE_NAME = "note_tag_text_rules"
EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME = "event_command_text_rule_groups"
EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME = "event_command_text_rule_filters"
EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME = "event_command_text_rule_paths"
FIELD_TRANSLATION_TERMS_TABLE_NAME = "terminology_field_terms"
TEXT_GLOSSARY_TERMS_TABLE_NAME = "text_glossary_terms"
TERMINOLOGY_BUNDLE_STATE_TABLE_NAME = "terminology_bundle_state"
PLACEHOLDER_RULES_TABLE_NAME = "placeholder_rules"
STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME = "structured_placeholder_rules"
STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME = "structured_placeholder_rule_groups"
SOURCE_RESIDUAL_RULES_TABLE_NAME = "source_residual_rules"
MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME = "mv_virtual_namebox_rules"
RULE_REVIEW_STATES_TABLE_NAME = "rule_review_states"
FONT_REPLACEMENT_RECORDS_TABLE_NAME = "font_replacement_records"
TRANSLATION_RUNS_TABLE_NAME = "translation_runs"
LLM_FAILURES_TABLE_NAME = "llm_failures"
TRANSLATION_QUALITY_ERRORS_TABLE_NAME = "translation_quality_errors"
TEXT_INDEX_META_TABLE_NAME = "text_index_meta"
TEXT_INDEX_ITEMS_TABLE_NAME = "text_index_items"
TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME = "text_index_scope_summary"
TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME = "text_index_domain_summary"
TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME = "text_index_rule_hit_summary"
TEXT_INDEX_INVALIDATIONS_TABLE_NAME = "text_index_invalidations"
METADATA_KEY = "current_game"
LANGUAGE_SETTINGS_KEY = "current"
SCHEMA_VERSION_KEY = "current"
TEXT_INDEX_META_KEY = "current"
CURRENT_SCHEMA_VERSION = 15
TERMINOLOGY_BUNDLE_STATE_KEY = "current"
EXPECTED_STATIC_TABLE_NAMES: tuple[str, ...] = (
    SCHEMA_VERSION_TABLE_NAME,
    TRANSLATION_TABLE_NAME,
    METADATA_TABLE_NAME,
    LANGUAGE_SETTINGS_TABLE_NAME,
    PLUGIN_TEXT_RULES_TABLE_NAME,
    PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME,
    NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME,
    PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME,
    PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME,
    SOURCE_SNAPSHOT_FILES_TABLE_NAME,
    NOTE_TAG_TEXT_RULES_TABLE_NAME,
    EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME,
    EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME,
    EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME,
    FIELD_TRANSLATION_TERMS_TABLE_NAME,
    TEXT_GLOSSARY_TERMS_TABLE_NAME,
    TERMINOLOGY_BUNDLE_STATE_TABLE_NAME,
    PLACEHOLDER_RULES_TABLE_NAME,
    STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME,
    STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME,
    SOURCE_RESIDUAL_RULES_TABLE_NAME,
    MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME,
    RULE_REVIEW_STATES_TABLE_NAME,
    FONT_REPLACEMENT_RECORDS_TABLE_NAME,
    TRANSLATION_RUNS_TABLE_NAME,
    LLM_FAILURES_TABLE_NAME,
    TRANSLATION_QUALITY_ERRORS_TABLE_NAME,
    TEXT_INDEX_META_TABLE_NAME,
    TEXT_INDEX_ITEMS_TABLE_NAME,
    TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME,
    TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME,
    TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME,
    TEXT_INDEX_INVALIDATIONS_TABLE_NAME,
)

CREATE_SCHEMA_VERSION_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{SCHEMA_VERSION_TABLE_NAME}] (
        schema_key TEXT PRIMARY KEY,
        version    INTEGER NOT NULL
    )
;
"""

CREATE_TRANSLATION_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TRANSLATION_TABLE_NAME}] (
        location_path      TEXT PRIMARY KEY,
        item_type          TEXT NOT NULL,
        role               TEXT,
        original_lines     TEXT NOT NULL,
        source_line_paths  TEXT NOT NULL,
        translation_lines  TEXT NOT NULL
    )
;
"""

CREATE_PLACEHOLDER_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{PLACEHOLDER_RULES_TABLE_NAME}] (
        pattern_text         TEXT PRIMARY KEY,
        placeholder_template TEXT NOT NULL
    )
;
"""

CREATE_STRUCTURED_PLACEHOLDER_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME}] (
        rule_name          TEXT PRIMARY KEY,
        rule_type          TEXT NOT NULL,
        pattern_text       TEXT NOT NULL,
        translatable_group TEXT NOT NULL
    )
;
"""

CREATE_STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME}] (
        rule_name            TEXT NOT NULL,
        group_name           TEXT NOT NULL,
        placeholder_template TEXT NOT NULL,
        PRIMARY KEY (rule_name, group_name),
        FOREIGN KEY (rule_name) REFERENCES [{STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME}](rule_name) ON DELETE CASCADE
    )
;
"""

CREATE_SOURCE_RESIDUAL_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{SOURCE_RESIDUAL_RULES_TABLE_NAME}] (
        rule_id       TEXT PRIMARY KEY,
        rule_type     TEXT NOT NULL,
        location_path TEXT NOT NULL,
        pattern_text  TEXT NOT NULL,
        allowed_terms TEXT NOT NULL,
        check_group   TEXT NOT NULL,
        reason        TEXT NOT NULL
    )
;
"""

CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME}] (
        rule_order      INTEGER NOT NULL,
        rule_name       TEXT NOT NULL,
        pattern_text    TEXT NOT NULL,
        speaker_group   TEXT NOT NULL,
        body_group      TEXT NOT NULL,
        speaker_policy  TEXT NOT NULL,
        render_template TEXT NOT NULL,
        PRIMARY KEY (rule_order),
        UNIQUE (rule_name)
    )
;
"""

CREATE_RULE_REVIEW_STATES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{RULE_REVIEW_STATES_TABLE_NAME}] (
        rule_domain    TEXT PRIMARY KEY,
        scope_hash     TEXT NOT NULL,
        reviewed_empty INTEGER NOT NULL,
        updated_at     TEXT NOT NULL
    )
;
"""

CREATE_FONT_REPLACEMENT_RECORDS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{FONT_REPLACEMENT_RECORDS_TABLE_NAME}] (
        file_name             TEXT NOT NULL,
        value_path            TEXT NOT NULL,
        original_text         TEXT NOT NULL,
        replaced_text         TEXT NOT NULL,
        replacement_font_name TEXT NOT NULL,
        PRIMARY KEY (file_name, value_path)
    )
;
"""

CREATE_TRANSLATION_RUNS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TRANSLATION_RUNS_TABLE_NAME}] (
        run_id            TEXT PRIMARY KEY,
        status            TEXT NOT NULL,
        total_extracted   INTEGER NOT NULL,
        pending_count     INTEGER NOT NULL,
        deduplicated_count INTEGER NOT NULL,
        batch_count       INTEGER NOT NULL,
        success_count     INTEGER NOT NULL,
        quality_error_count INTEGER NOT NULL,
        llm_failure_count INTEGER NOT NULL,
        started_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL,
        finished_at       TEXT,
        stop_reason       TEXT NOT NULL,
        last_error        TEXT NOT NULL
    )
;
"""

CREATE_LLM_FAILURES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{LLM_FAILURES_TABLE_NAME}] (
        failure_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          TEXT NOT NULL,
        category        TEXT NOT NULL,
        error_type      TEXT NOT NULL,
        error_message   TEXT NOT NULL,
        retryable       INTEGER NOT NULL,
        attempt_count   INTEGER NOT NULL,
        created_at      TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES [{TRANSLATION_RUNS_TABLE_NAME}](run_id) ON DELETE CASCADE
    )
;
"""

CREATE_TRANSLATION_QUALITY_ERRORS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] (
        run_id           TEXT NOT NULL,
        location_path    TEXT NOT NULL,
        item_type        TEXT NOT NULL,
        role             TEXT,
        original_lines   TEXT NOT NULL,
        translation_lines TEXT NOT NULL,
        error_type       TEXT NOT NULL,
        error_detail     TEXT NOT NULL,
        model_response   TEXT NOT NULL,
        PRIMARY KEY (run_id, location_path),
        FOREIGN KEY (run_id) REFERENCES [{TRANSLATION_RUNS_TABLE_NAME}](run_id) ON DELETE CASCADE
    )
;
"""

CREATE_TEXT_INDEX_META_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_META_TABLE_NAME}] (
        index_key                   TEXT PRIMARY KEY,
        source_snapshot_fingerprint TEXT NOT NULL,
        rules_fingerprint           TEXT NOT NULL,
        item_count                  INTEGER NOT NULL,
        workflow_gate_scope_hashes  TEXT NOT NULL,
        created_at                  TEXT NOT NULL
    )
;
"""

CREATE_TEXT_INDEX_ITEMS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_ITEMS_TABLE_NAME}] (
        location_path               TEXT PRIMARY KEY,
        item_type                   TEXT NOT NULL CHECK (item_type IN ('long_text', 'array', 'short_text')),
        role                        TEXT,
        original_lines              TEXT NOT NULL,
        source_line_paths           TEXT NOT NULL,
        source_type                 TEXT NOT NULL,
        source_file                 TEXT NOT NULL,
        writable                    INTEGER NOT NULL CHECK (writable IN (0, 1)),
        source_snapshot_fingerprint TEXT NOT NULL,
        rules_fingerprint           TEXT NOT NULL,
        locator_json                TEXT NOT NULL
    )
;
"""

CREATE_TEXT_INDEX_SCOPE_SUMMARY_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME}] (
        index_key           TEXT PRIMARY KEY,
        total_count         INTEGER NOT NULL,
        active_count        INTEGER NOT NULL,
        writable_count      INTEGER NOT NULL,
        unwritable_count    INTEGER NOT NULL,
        stale_rule_count    INTEGER NOT NULL,
        native_thread_count INTEGER NOT NULL
    )
;
"""

CREATE_TEXT_INDEX_DOMAIN_SUMMARY_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME}] (
        domain                  TEXT PRIMARY KEY,
        item_count              INTEGER NOT NULL,
        active_count            INTEGER NOT NULL,
        writable_count          INTEGER NOT NULL,
        unwritable_count        INTEGER NOT NULL,
        inactive_rule_hit_count INTEGER NOT NULL
    )
;
"""

CREATE_TEXT_INDEX_RULE_HIT_SUMMARY_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME}] (
        domain            TEXT NOT NULL,
        rule_key          TEXT NOT NULL,
        hit_count         INTEGER NOT NULL,
        extractable_count INTEGER NOT NULL,
        writable_count    INTEGER NOT NULL,
        unwritable_count  INTEGER NOT NULL,
        PRIMARY KEY (domain, rule_key)
    )
;
"""

CREATE_TEXT_INDEX_INVALIDATIONS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_INDEX_INVALIDATIONS_TABLE_NAME}] (
        reason_key TEXT PRIMARY KEY,
        detail     TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
;
"""

CREATE_METADATA_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{METADATA_TABLE_NAME}] (
        metadata_key TEXT PRIMARY KEY,
        game_title   TEXT NOT NULL,
        game_path    TEXT NOT NULL,
        engine_kind  TEXT NOT NULL,
        content_root TEXT NOT NULL,
        engine_version TEXT NOT NULL
    )
;
"""

CREATE_LANGUAGE_SETTINGS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{LANGUAGE_SETTINGS_TABLE_NAME}] (
        settings_key    TEXT PRIMARY KEY,
        source_language TEXT NOT NULL,
        target_language TEXT NOT NULL
    )
;
"""

CREATE_PLUGIN_TEXT_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{PLUGIN_TEXT_RULES_TABLE_NAME}] (
        plugin_index  INTEGER NOT NULL,
        plugin_name   TEXT NOT NULL,
        plugin_hash   TEXT NOT NULL,
        path_template TEXT NOT NULL,
        PRIMARY KEY (plugin_index, path_template)
    )
;
"""

CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME}] (
        file_name TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        selector  TEXT NOT NULL,
        selector_kind TEXT NOT NULL CHECK (selector_kind IN ('translate', 'excluded')),
        PRIMARY KEY (file_name, selector)
    )
;
"""

CREATE_NONSTANDARD_DATA_TEXT_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME}] (
        file_name     TEXT NOT NULL,
        file_hash     TEXT NOT NULL,
        path_template TEXT NOT NULL,
        path_kind     TEXT NOT NULL CHECK (path_kind IN ('translate', 'excluded', 'skipped')),
        PRIMARY KEY (file_name, path_kind, path_template)
    )
;
"""

CREATE_PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME}] (
        location_path          TEXT PRIMARY KEY,
        mapping_kind           TEXT NOT NULL CHECK (mapping_kind IN ('translated', 'excluded')),
        source_file_name       TEXT NOT NULL,
        source_selector        TEXT NOT NULL,
        source_file_hash       TEXT NOT NULL,
        source_text_hash       TEXT NOT NULL,
        translation_lines_hash TEXT NOT NULL,
        runtime_file_name      TEXT NOT NULL,
        runtime_selector       TEXT NOT NULL,
        runtime_file_hash      TEXT NOT NULL,
        runtime_text_hash      TEXT NOT NULL,
        runtime_line           INTEGER NOT NULL,
        created_at             TEXT NOT NULL,
        UNIQUE (runtime_file_name, runtime_selector)
    )
;
"""

CREATE_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}] (
        file_name    TEXT PRIMARY KEY,
        file_hash    TEXT NOT NULL,
        syntax_error TEXT NOT NULL,
        literals_json TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )
;
"""

CREATE_SOURCE_SNAPSHOT_FILES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{SOURCE_SNAPSHOT_FILES_TABLE_NAME}] (
        relative_path TEXT PRIMARY KEY,
        sha256        TEXT NOT NULL,
        byte_size     INTEGER NOT NULL,
        updated_at    TEXT NOT NULL
    )
;
"""

CREATE_NOTE_TAG_TEXT_RULES_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{NOTE_TAG_TEXT_RULES_TABLE_NAME}] (
        file_name TEXT NOT NULL,
        tag_name  TEXT NOT NULL,
        PRIMARY KEY (file_name, tag_name)
    )
;
"""

CREATE_EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}] (
        group_key    TEXT PRIMARY KEY,
        command_code INTEGER NOT NULL
    )
;
"""

CREATE_EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME}] (
        group_key       TEXT NOT NULL,
        parameter_index INTEGER NOT NULL,
        parameter_value TEXT NOT NULL,
        PRIMARY KEY (group_key, parameter_index),
        FOREIGN KEY (group_key) REFERENCES [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}](group_key) ON DELETE CASCADE
    )
;
"""

CREATE_EVENT_COMMAND_TEXT_RULE_PATHS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME}] (
        group_key     TEXT NOT NULL,
        path_template TEXT NOT NULL,
        PRIMARY KEY (group_key, path_template),
        FOREIGN KEY (group_key) REFERENCES [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}](group_key) ON DELETE CASCADE
    )
;
"""

CREATE_FIELD_TRANSLATION_TERMS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{FIELD_TRANSLATION_TERMS_TABLE_NAME}] (
        category        TEXT NOT NULL,
        source_text     TEXT NOT NULL,
        translated_text TEXT NOT NULL,
        PRIMARY KEY (category, source_text)
    )
;
"""

CREATE_TEXT_GLOSSARY_TERMS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_GLOSSARY_TERMS_TABLE_NAME}] (
        source_text     TEXT PRIMARY KEY,
        translated_text TEXT NOT NULL
    )
;
"""

CREATE_TERMINOLOGY_BUNDLE_STATE_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TERMINOLOGY_BUNDLE_STATE_TABLE_NAME}] (
        state_key TEXT PRIMARY KEY,
        imported  INTEGER NOT NULL
    )
;
"""

INSERT_TRANSLATION = f"""
--sql
    INSERT OR REPLACE INTO [{TRANSLATION_TABLE_NAME}]
    (location_path, item_type, role, original_lines, source_line_paths, translation_lines)
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

UPSERT_METADATA = f"""
--sql
    INSERT OR REPLACE INTO [{METADATA_TABLE_NAME}]
    (metadata_key, game_title, game_path, engine_kind, content_root, engine_version)
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

UPSERT_LANGUAGE_SETTINGS = f"""
--sql
    INSERT OR REPLACE INTO [{LANGUAGE_SETTINGS_TABLE_NAME}]
    (settings_key, source_language, target_language)
    VALUES (?, ?, ?)
;
"""

INSERT_PLUGIN_TEXT_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{PLUGIN_TEXT_RULES_TABLE_NAME}]
    (plugin_index, plugin_name, plugin_hash, path_template)
    VALUES (?, ?, ?, ?)
;
"""

INSERT_PLUGIN_SOURCE_TEXT_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME}]
    (file_name, file_hash, selector, selector_kind)
    VALUES (?, ?, ?, ?)
;
"""

INSERT_NONSTANDARD_DATA_TEXT_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME}]
    (file_name, file_hash, path_template, path_kind)
    VALUES (?, ?, ?, ?)
;
"""

INSERT_PLUGIN_SOURCE_RUNTIME_WRITE_MAP = f"""
--sql
    INSERT OR REPLACE INTO [{PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME}]
    (
        location_path,
        mapping_kind,
        source_file_name,
        source_selector,
        source_file_hash,
        source_text_hash,
        translation_lines_hash,
        runtime_file_name,
        runtime_selector,
        runtime_file_hash,
        runtime_text_hash,
        runtime_line,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_SOURCE_SNAPSHOT_FILE = f"""
--sql
    INSERT OR REPLACE INTO [{SOURCE_SNAPSHOT_FILES_TABLE_NAME}]
    (relative_path, sha256, byte_size, updated_at)
    VALUES (?, ?, ?, ?)
;
"""

DELETE_ALL_SOURCE_SNAPSHOT_FILES = f"""
--sql
    DELETE FROM [{SOURCE_SNAPSHOT_FILES_TABLE_NAME}]
;
"""

INSERT_NOTE_TAG_TEXT_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{NOTE_TAG_TEXT_RULES_TABLE_NAME}]
    (file_name, tag_name)
    VALUES (?, ?)
;
"""

INSERT_EVENT_COMMAND_TEXT_RULE_GROUP = f"""
--sql
    INSERT OR REPLACE INTO [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}]
    (group_key, command_code)
    VALUES (?, ?)
;
"""

INSERT_EVENT_COMMAND_TEXT_RULE_FILTER = f"""
--sql
    INSERT OR REPLACE INTO [{EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME}]
    (group_key, parameter_index, parameter_value)
    VALUES (?, ?, ?)
;
"""

INSERT_EVENT_COMMAND_TEXT_RULE_PATH = f"""
--sql
    INSERT OR REPLACE INTO [{EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME}]
    (group_key, path_template)
    VALUES (?, ?)
;
"""

UPSERT_SCHEMA_VERSION = f"""
--sql
    INSERT OR REPLACE INTO [{SCHEMA_VERSION_TABLE_NAME}]
    (schema_key, version)
    VALUES (?, ?)
;
"""

INSERT_FIELD_TRANSLATION_TERM = f"""
--sql
    INSERT OR REPLACE INTO [{FIELD_TRANSLATION_TERMS_TABLE_NAME}]
    (category, source_text, translated_text)
    VALUES (?, ?, ?)
;
"""

INSERT_TEXT_GLOSSARY_TERM = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_GLOSSARY_TERMS_TABLE_NAME}]
    (source_text, translated_text)
    VALUES (?, ?)
;
"""

UPSERT_TERMINOLOGY_BUNDLE_STATE = f"""
--sql
    INSERT OR REPLACE INTO [{TERMINOLOGY_BUNDLE_STATE_TABLE_NAME}]
    (state_key, imported)
    VALUES (?, ?)
;
"""

INSERT_PLACEHOLDER_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{PLACEHOLDER_RULES_TABLE_NAME}]
    (pattern_text, placeholder_template)
    VALUES (?, ?)
;
"""

INSERT_STRUCTURED_PLACEHOLDER_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME}]
    (rule_name, rule_type, pattern_text, translatable_group)
    VALUES (?, ?, ?, ?)
;
"""

INSERT_STRUCTURED_PLACEHOLDER_RULE_GROUP = f"""
--sql
    INSERT OR REPLACE INTO [{STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME}]
    (rule_name, group_name, placeholder_template)
    VALUES (?, ?, ?)
;
"""

INSERT_SOURCE_RESIDUAL_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{SOURCE_RESIDUAL_RULES_TABLE_NAME}]
    (rule_id, rule_type, location_path, pattern_text, allowed_terms, check_group, reason)
    VALUES (?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_MV_VIRTUAL_NAMEBOX_RULE = f"""
--sql
    INSERT OR REPLACE INTO [{MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME}]
    (rule_order, rule_name, pattern_text, speaker_group, body_group, speaker_policy, render_template)
    VALUES (?, ?, ?, ?, ?, ?, ?)
;
"""

UPSERT_RULE_REVIEW_STATE = f"""
--sql
    INSERT OR REPLACE INTO [{RULE_REVIEW_STATES_TABLE_NAME}]
    (rule_domain, scope_hash, reviewed_empty, updated_at)
    VALUES (?, ?, ?, ?)
;
"""

INSERT_FONT_REPLACEMENT_RECORD = f"""
--sql
    INSERT OR REPLACE INTO [{FONT_REPLACEMENT_RECORDS_TABLE_NAME}]
    (file_name, value_path, original_text, replaced_text, replacement_font_name)
    VALUES (?, ?, ?, ?, ?)
;
"""

UPSERT_TRANSLATION_RUN = f"""
--sql
    INSERT INTO [{TRANSLATION_RUNS_TABLE_NAME}]
    (
        run_id,
        status,
        total_extracted,
        pending_count,
        deduplicated_count,
        batch_count,
        success_count,
        quality_error_count,
        llm_failure_count,
        started_at,
        updated_at,
        finished_at,
        stop_reason,
        last_error
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
        status = excluded.status,
        total_extracted = excluded.total_extracted,
        pending_count = excluded.pending_count,
        deduplicated_count = excluded.deduplicated_count,
        batch_count = excluded.batch_count,
        success_count = excluded.success_count,
        quality_error_count = excluded.quality_error_count,
        llm_failure_count = excluded.llm_failure_count,
        started_at = excluded.started_at,
        updated_at = excluded.updated_at,
        finished_at = excluded.finished_at,
        stop_reason = excluded.stop_reason,
        last_error = excluded.last_error
;
"""

INSERT_LLM_FAILURE = f"""
--sql
    INSERT INTO [{LLM_FAILURES_TABLE_NAME}]
    (run_id, category, error_type, error_message, retryable, attempt_count, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_TRANSLATION_QUALITY_ERROR = f"""
--sql
    INSERT OR REPLACE INTO [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
    (run_id, location_path, item_type, role, original_lines, translation_lines, error_type, error_detail, model_response)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

UPSERT_TEXT_INDEX_META = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_META_TABLE_NAME}]
    (index_key, source_snapshot_fingerprint, rules_fingerprint, item_count, workflow_gate_scope_hashes, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_INDEX_ITEM = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_ITEMS_TABLE_NAME}]
    (
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_type,
        source_file,
        writable,
        source_snapshot_fingerprint,
        rules_fingerprint,
        locator_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

UPSERT_TEXT_INDEX_SCOPE_SUMMARY = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME}]
    (
        index_key,
        total_count,
        active_count,
        writable_count,
        unwritable_count,
        stale_rule_count,
        native_thread_count
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_INDEX_DOMAIN_SUMMARY = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME}]
    (
        domain,
        item_count,
        active_count,
        writable_count,
        unwritable_count,
        inactive_rule_hit_count
    )
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_INDEX_RULE_HIT_SUMMARY = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME}]
    (
        domain,
        rule_key,
        hit_count,
        extractable_count,
        writable_count,
        unwritable_count
    )
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_INDEX_INVALIDATION = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_INVALIDATIONS_TABLE_NAME}]
    (reason_key, detail, created_at)
    VALUES (?, ?, ?)
;
"""

DELETE_ALL_TRANSLATION_QUALITY_ERRORS = f"""
--sql
    DELETE FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_META = f"""
--sql
    DELETE FROM [{TEXT_INDEX_META_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_ITEMS = f"""
--sql
    DELETE FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_SCOPE_SUMMARY = f"""
--sql
    DELETE FROM [{TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_DOMAIN_SUMMARY = f"""
--sql
    DELETE FROM [{TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_RULE_HIT_SUMMARY = f"""
--sql
    DELETE FROM [{TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_INDEX_INVALIDATIONS = f"""
--sql
    DELETE FROM [{TEXT_INDEX_INVALIDATIONS_TABLE_NAME}]
;
"""

SELECT_TRANSLATION_PATHS = f"""
--sql
    SELECT location_path
    FROM [{TRANSLATION_TABLE_NAME}]
;
"""

COUNT_TRANSLATED_ITEMS = f"""
--sql
    SELECT COUNT(*) AS translated_count
    FROM [{TRANSLATION_TABLE_NAME}]
;
"""

SELECT_TRANSLATED_ITEMS = f"""
--sql
    SELECT location_path, item_type, role, original_lines, source_line_paths, translation_lines
    FROM [{TRANSLATION_TABLE_NAME}]
    ORDER BY location_path
;
"""

SELECT_TRANSLATED_ITEMS_BY_PREFIX = f"""
--sql
    SELECT location_path, item_type, role, original_lines, source_line_paths, translation_lines
    FROM [{TRANSLATION_TABLE_NAME}]
    WHERE location_path LIKE ?
    ORDER BY location_path
;
"""

SELECT_TRANSLATED_ITEM_BY_PATH = f"""
--sql
    SELECT location_path, item_type, role, original_lines, source_line_paths, translation_lines
    FROM [{TRANSLATION_TABLE_NAME}]
    WHERE location_path = ?
    LIMIT 1
;
"""

SELECT_METADATA = f"""
--sql
    SELECT game_title, game_path, engine_kind, content_root, engine_version
    FROM [{METADATA_TABLE_NAME}]
    WHERE metadata_key = ?
    LIMIT 1
;
"""

SELECT_LANGUAGE_SETTINGS = f"""
--sql
    SELECT source_language, target_language
    FROM [{LANGUAGE_SETTINGS_TABLE_NAME}]
    WHERE settings_key = ?
    LIMIT 1
;
"""

SELECT_PLUGIN_TEXT_RULES = f"""
--sql
    SELECT plugin_index, plugin_name, plugin_hash, path_template
    FROM [{PLUGIN_TEXT_RULES_TABLE_NAME}]
    ORDER BY plugin_index, path_template
;
"""

SELECT_PLUGIN_SOURCE_TEXT_RULES = f"""
--sql
    SELECT file_name, file_hash, selector, selector_kind
    FROM [{PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME}]
    ORDER BY file_name, selector_kind, selector
;
"""

SELECT_NONSTANDARD_DATA_TEXT_RULES = f"""
--sql
    SELECT file_name, file_hash, path_template, path_kind
    FROM [{NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME}]
    ORDER BY file_name, path_kind, path_template
;
"""

SELECT_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS = f"""
--sql
    SELECT
        location_path,
        mapping_kind,
        source_file_name,
        source_selector,
        source_file_hash,
        source_text_hash,
        translation_lines_hash,
        runtime_file_name,
        runtime_selector,
        runtime_file_hash,
        runtime_text_hash,
        runtime_line,
        created_at
    FROM [{PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME}]
    ORDER BY runtime_file_name, runtime_selector, location_path
;
"""

SELECT_SOURCE_SNAPSHOT_FILES = f"""
--sql
    SELECT relative_path, sha256, byte_size, updated_at
    FROM [{SOURCE_SNAPSHOT_FILES_TABLE_NAME}]
    ORDER BY relative_path
;
"""

SELECT_NOTE_TAG_TEXT_RULES = f"""
--sql
    SELECT file_name, tag_name
    FROM [{NOTE_TAG_TEXT_RULES_TABLE_NAME}]
    ORDER BY file_name, tag_name
;
"""

SELECT_EVENT_COMMAND_TEXT_RULE_GROUPS = f"""
--sql
    SELECT group_key, command_code
    FROM [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}]
    ORDER BY group_key
;
"""

SELECT_EVENT_COMMAND_TEXT_RULE_FILTERS = f"""
--sql
    SELECT group_key, parameter_index, parameter_value
    FROM [{EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME}]
    ORDER BY group_key, parameter_index
;
"""

SELECT_EVENT_COMMAND_TEXT_RULE_PATHS = f"""
--sql
    SELECT group_key, path_template
    FROM [{EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME}]
    ORDER BY group_key, path_template
;
"""

SELECT_SCHEMA_VERSION = f"""
--sql
    SELECT version
    FROM [{SCHEMA_VERSION_TABLE_NAME}]
    WHERE schema_key = ?
    LIMIT 1
;
"""

SELECT_FIELD_TRANSLATION_TERMS = f"""
--sql
    SELECT category, source_text, translated_text
    FROM [{FIELD_TRANSLATION_TERMS_TABLE_NAME}]
    ORDER BY category, source_text
;
"""

SELECT_TEXT_GLOSSARY_TERMS = f"""
--sql
    SELECT source_text, translated_text
    FROM [{TEXT_GLOSSARY_TERMS_TABLE_NAME}]
    ORDER BY source_text
;
"""

SELECT_TERMINOLOGY_BUNDLE_STATE = f"""
--sql
    SELECT state_key
    FROM [{TERMINOLOGY_BUNDLE_STATE_TABLE_NAME}]
    WHERE state_key = ?
    LIMIT 1
;
"""

SELECT_TABLE_NAMES = """
--sql
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
;
"""

SELECT_PLACEHOLDER_RULES = f"""
--sql
    SELECT pattern_text, placeholder_template
    FROM [{PLACEHOLDER_RULES_TABLE_NAME}]
    ORDER BY pattern_text
;
"""

SELECT_STRUCTURED_PLACEHOLDER_RULES = f"""
--sql
    SELECT rule_name, rule_type, pattern_text, translatable_group
    FROM [{STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME}]
    ORDER BY rule_name
;
"""

SELECT_STRUCTURED_PLACEHOLDER_RULE_GROUPS = f"""
--sql
    SELECT rule_name, group_name, placeholder_template
    FROM [{STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME}]
    ORDER BY rule_name, group_name
;
"""

SELECT_SOURCE_RESIDUAL_RULES = f"""
--sql
    SELECT rule_id, rule_type, location_path, pattern_text, allowed_terms, check_group, reason
    FROM [{SOURCE_RESIDUAL_RULES_TABLE_NAME}]
    ORDER BY rule_type, rule_id
;
"""

SELECT_MV_VIRTUAL_NAMEBOX_RULES = f"""
--sql
    SELECT rule_order, rule_name, pattern_text, speaker_group, body_group, speaker_policy, render_template
    FROM [{MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME}]
    ORDER BY rule_order
;
"""

SELECT_RULE_REVIEW_STATE = f"""
--sql
    SELECT rule_domain, scope_hash, reviewed_empty, updated_at
    FROM [{RULE_REVIEW_STATES_TABLE_NAME}]
    WHERE rule_domain = ?
    LIMIT 1
;
"""

SELECT_FONT_REPLACEMENT_RECORDS = f"""
--sql
    SELECT file_name, value_path, original_text, replaced_text, replacement_font_name
    FROM [{FONT_REPLACEMENT_RECORDS_TABLE_NAME}]
    ORDER BY file_name, value_path
;
"""

SELECT_LATEST_TRANSLATION_RUN = f"""
--sql
    SELECT *
    FROM [{TRANSLATION_RUNS_TABLE_NAME}]
    ORDER BY started_at DESC, run_id DESC
    LIMIT 1
;
"""

SELECT_TRANSLATION_RUN = f"""
--sql
    SELECT *
    FROM [{TRANSLATION_RUNS_TABLE_NAME}]
    WHERE run_id = ?
    LIMIT 1
;
"""

SELECT_LLM_FAILURES_BY_RUN = f"""
--sql
    SELECT *
    FROM [{LLM_FAILURES_TABLE_NAME}]
    WHERE run_id = ?
    ORDER BY failure_id
;
"""

SELECT_TRANSLATION_QUALITY_ERRORS_BY_RUN = f"""
--sql
    SELECT *
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
    WHERE run_id = ?
    ORDER BY location_path
;
"""

SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS = f"""
--sql
    SELECT quality_errors.location_path
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
    INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
        ON index_items.location_path = quality_errors.location_path
    LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
        ON translations.location_path = quality_errors.location_path
    WHERE quality_errors.run_id = ?
        AND index_items.writable = 1
        AND translations.location_path IS NULL
    ORDER BY quality_errors.location_path
;
"""

SELECT_TRANSLATION_QUALITY_ERROR_BY_RUN_AND_PATH = f"""
--sql
    SELECT *
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
    WHERE run_id = ? AND location_path = ?
    LIMIT 1
;
"""

COUNT_TRANSLATION_QUALITY_ERRORS_BY_RUN = f"""
--sql
    SELECT COUNT(*) AS quality_error_count
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
    WHERE run_id = ?
;
"""

SELECT_TRANSLATION_QUALITY_ERROR_TYPE_COUNTS_BY_RUN = f"""
--sql
    SELECT error_type, COUNT(*) AS error_count
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
    WHERE run_id = ?
    GROUP BY error_type
    ORDER BY error_type
;
"""

SELECT_TEXT_INDEX_META = f"""
--sql
    SELECT source_snapshot_fingerprint, rules_fingerprint, item_count, workflow_gate_scope_hashes, created_at
    FROM [{TEXT_INDEX_META_TABLE_NAME}]
    WHERE index_key = ?
    LIMIT 1
;
"""

SELECT_TEXT_INDEX_ITEMS = f"""
--sql
    SELECT
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_type,
        source_file,
        writable,
        source_snapshot_fingerprint,
        rules_fingerprint,
        locator_json
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
    ORDER BY location_path
;
"""

SELECT_TEXT_INDEX_SCOPE_SUMMARY = f"""
--sql
    SELECT
        total_count,
        active_count,
        writable_count,
        unwritable_count,
        stale_rule_count,
        native_thread_count
    FROM [{TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME}]
    WHERE index_key = ?
    LIMIT 1
;
"""

SELECT_TEXT_INDEX_DOMAIN_SUMMARY = f"""
--sql
    SELECT
        domain,
        item_count,
        active_count,
        writable_count,
        unwritable_count,
        inactive_rule_hit_count
    FROM [{TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME}]
    ORDER BY domain
;
"""

SELECT_TEXT_INDEX_RULE_HIT_SUMMARY = f"""
--sql
    SELECT
        domain,
        rule_key,
        hit_count,
        extractable_count,
        writable_count,
        unwritable_count
    FROM [{TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME}]
    ORDER BY domain, rule_key
;
"""

SELECT_TEXT_INDEX_ITEM_COUNT = f"""
--sql
    SELECT COUNT(*) AS item_count
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
;
"""

COUNT_TEXT_INDEX_TRANSLATED_ITEMS = f"""
--sql
    SELECT COUNT(*) AS translated_count
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
    INNER JOIN [{TRANSLATION_TABLE_NAME}] AS translations
        ON translations.location_path = index_items.location_path
;
"""

COUNT_PENDING_TEXT_INDEX_QUALITY_ERRORS = f"""
--sql
    SELECT COUNT(*) AS quality_error_count
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
    INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
        ON index_items.location_path = quality_errors.location_path
    LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
        ON translations.location_path = quality_errors.location_path
    WHERE quality_errors.run_id = ?
        AND index_items.writable = 1
        AND translations.location_path IS NULL
;
"""

SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_TYPE_COUNTS = f"""
--sql
    SELECT quality_errors.error_type, COUNT(*) AS error_count
    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
    INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
        ON index_items.location_path = quality_errors.location_path
    LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
        ON translations.location_path = quality_errors.location_path
    WHERE quality_errors.run_id = ?
        AND index_items.writable = 1
        AND translations.location_path IS NULL
    GROUP BY quality_errors.error_type
    ORDER BY quality_errors.error_type
;
"""

SELECT_PENDING_TEXT_INDEX_ITEMS = f"""
--sql
    SELECT
        indexed.location_path,
        indexed.item_type,
        indexed.role,
        indexed.original_lines,
        indexed.source_line_paths,
        indexed.source_type,
        indexed.source_file,
        indexed.writable,
        indexed.source_snapshot_fingerprint,
        indexed.rules_fingerprint,
        indexed.locator_json
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
    LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translated
        ON translated.location_path = indexed.location_path
    WHERE translated.location_path IS NULL
        AND indexed.writable = 1
    ORDER BY indexed.location_path
    LIMIT ?
;
"""

SELECT_PENDING_TEXT_INDEX_COUNT = f"""
--sql
    SELECT COUNT(*) AS pending_count
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
    LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translated
        ON translated.location_path = indexed.location_path
    WHERE translated.location_path IS NULL
        AND indexed.writable = 1
;
"""

SELECT_TEXT_INDEX_ITEM_BY_PATH = f"""
--sql
    SELECT
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_type,
        source_file,
        writable,
        source_snapshot_fingerprint,
        rules_fingerprint,
        locator_json
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
    WHERE location_path = ?
    LIMIT 1
;
"""

SELECT_TEXT_INDEX_LOCATION_PATHS = f"""
--sql
    SELECT location_path
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
;
"""

SELECT_WRITABLE_TEXT_INDEX_LOCATION_PATHS = f"""
--sql
    SELECT location_path
    FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
    WHERE writable = 1
    ORDER BY location_path
;
"""

COUNT_TRANSLATIONS_OUTSIDE_WRITABLE_TEXT_INDEX = f"""
--sql
    SELECT COUNT(*) AS stale_translation_count
    FROM [{TRANSLATION_TABLE_NAME}] AS translations
    LEFT JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
        ON index_items.location_path = translations.location_path
        AND index_items.writable = 1
    WHERE index_items.location_path IS NULL
;
"""

SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX = f"""
--sql
    SELECT
        translations.location_path,
        translations.item_type,
        translations.role,
        translations.original_lines,
        translations.source_line_paths,
        translations.translation_lines
    FROM [{TRANSLATION_TABLE_NAME}] AS translations
    INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS index_items
        ON index_items.location_path = translations.location_path
    WHERE index_items.writable = 1
    ORDER BY translations.location_path
;
"""

SELECT_TEXT_INDEX_INVALIDATIONS = f"""
--sql
    SELECT reason_key, detail, created_at
    FROM [{TEXT_INDEX_INVALIDATIONS_TABLE_NAME}]
    ORDER BY reason_key
;
"""

DELETE_ALL_PLUGIN_TEXT_RULES = f"""
--sql
    DELETE FROM [{PLUGIN_TEXT_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_PLUGIN_SOURCE_TEXT_RULES = f"""
--sql
    DELETE FROM [{PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_NONSTANDARD_DATA_TEXT_RULES = f"""
--sql
    DELETE FROM [{NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS = f"""
--sql
    DELETE FROM [{PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME}]
;
"""

INSERT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE = f"""
--sql
    INSERT OR REPLACE INTO [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}]
    (file_name, file_hash, syntax_error, literals_json, created_at)
    VALUES (?, ?, ?, ?, ?)
;
"""

SELECT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE = f"""
--sql
    SELECT file_name, file_hash, syntax_error, literals_json, created_at
    FROM [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}]
    ORDER BY file_name
;
"""

DELETE_ALL_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE = f"""
--sql
    DELETE FROM [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}]
;
"""

DELETE_ALL_NOTE_TAG_TEXT_RULES = f"""
--sql
    DELETE FROM [{NOTE_TAG_TEXT_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_EVENT_COMMAND_TEXT_RULE_PATHS = f"""
--sql
    DELETE FROM [{EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME}]
;
"""

DELETE_ALL_EVENT_COMMAND_TEXT_RULE_FILTERS = f"""
--sql
    DELETE FROM [{EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME}]
;
"""

DELETE_ALL_EVENT_COMMAND_TEXT_RULE_GROUPS = f"""
--sql
    DELETE FROM [{EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME}]
;
"""

DELETE_ALL_FIELD_TRANSLATION_TERMS = f"""
--sql
    DELETE FROM [{FIELD_TRANSLATION_TERMS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_GLOSSARY_TERMS = f"""
--sql
    DELETE FROM [{TEXT_GLOSSARY_TERMS_TABLE_NAME}]
;
"""

DELETE_ALL_PLACEHOLDER_RULES = f"""
--sql
    DELETE FROM [{PLACEHOLDER_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_STRUCTURED_PLACEHOLDER_RULE_GROUPS = f"""
--sql
    DELETE FROM [{STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME}]
;
"""

DELETE_ALL_STRUCTURED_PLACEHOLDER_RULES = f"""
--sql
    DELETE FROM [{STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_SOURCE_RESIDUAL_RULES = f"""
--sql
    DELETE FROM [{SOURCE_RESIDUAL_RULES_TABLE_NAME}]
;
"""

DELETE_ALL_MV_VIRTUAL_NAMEBOX_RULES = f"""
--sql
    DELETE FROM [{MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME}]
;
"""

DELETE_RULE_REVIEW_STATE = f"""
--sql
    DELETE FROM [{RULE_REVIEW_STATES_TABLE_NAME}]
    WHERE rule_domain = ?
;
"""

DELETE_ALL_FONT_REPLACEMENT_RECORDS = f"""
--sql
    DELETE FROM [{FONT_REPLACEMENT_RECORDS_TABLE_NAME}]
;
"""

DELETE_TRANSLATION_ITEMS_BY_PREFIX = f"""
--sql
    DELETE FROM [{TRANSLATION_TABLE_NAME}]
    WHERE location_path LIKE ?
;
"""

DELETE_TRANSLATION_ITEM_BY_PATH = f"""
--sql
    DELETE FROM [{TRANSLATION_TABLE_NAME}]
    WHERE location_path = ?
;
"""

CHECK_CONNECTION_READABLE = """
--sql
    SELECT 1
;
"""

__all__: list[str] = [
    "CHECK_CONNECTION_READABLE",
    "CREATE_SCHEMA_VERSION_TABLE",
    "CREATE_EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE",
    "CREATE_EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE",
    "CREATE_EVENT_COMMAND_TEXT_RULE_PATHS_TABLE",
    "CREATE_FONT_REPLACEMENT_RECORDS_TABLE",
    "CREATE_LLM_FAILURES_TABLE",
    "CREATE_SOURCE_RESIDUAL_RULES_TABLE",
    "CREATE_LANGUAGE_SETTINGS_TABLE",
    "CREATE_METADATA_TABLE",
    "CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE",
    "CREATE_NONSTANDARD_DATA_TEXT_RULES_TABLE",
    "CREATE_NOTE_TAG_TEXT_RULES_TABLE",
    "CREATE_PLACEHOLDER_RULES_TABLE",
    "CREATE_PLUGIN_TEXT_RULES_TABLE",
    "CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE",
    "CREATE_PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE",
    "CREATE_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE",
    "CREATE_SOURCE_SNAPSHOT_FILES_TABLE",
    "CREATE_RULE_REVIEW_STATES_TABLE",
    "CREATE_STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE",
    "CREATE_STRUCTURED_PLACEHOLDER_RULES_TABLE",
    "CREATE_TRANSLATION_QUALITY_ERRORS_TABLE",
    "CREATE_TRANSLATION_RUNS_TABLE",
    "CREATE_TRANSLATION_TABLE",
    "CREATE_TEXT_INDEX_INVALIDATIONS_TABLE",
    "CREATE_TEXT_INDEX_DOMAIN_SUMMARY_TABLE",
    "CREATE_TEXT_INDEX_ITEMS_TABLE",
    "CREATE_TEXT_INDEX_META_TABLE",
    "CREATE_TEXT_INDEX_RULE_HIT_SUMMARY_TABLE",
    "CREATE_TEXT_INDEX_SCOPE_SUMMARY_TABLE",
    "CREATE_TERMINOLOGY_BUNDLE_STATE_TABLE",
    "CREATE_FIELD_TRANSLATION_TERMS_TABLE",
    "CREATE_TEXT_GLOSSARY_TERMS_TABLE",
    "DELETE_ALL_PLACEHOLDER_RULES",
    "DELETE_ALL_STRUCTURED_PLACEHOLDER_RULE_GROUPS",
    "DELETE_ALL_STRUCTURED_PLACEHOLDER_RULES",
    "DELETE_ALL_FONT_REPLACEMENT_RECORDS",
    "DELETE_ALL_MV_VIRTUAL_NAMEBOX_RULES",
    "DELETE_ALL_NONSTANDARD_DATA_TEXT_RULES",
    "DELETE_ALL_SOURCE_RESIDUAL_RULES",
    "DELETE_ALL_EVENT_COMMAND_TEXT_RULE_FILTERS",
    "DELETE_ALL_EVENT_COMMAND_TEXT_RULE_GROUPS",
    "DELETE_ALL_EVENT_COMMAND_TEXT_RULE_PATHS",
    "DELETE_ALL_NOTE_TAG_TEXT_RULES",
    "DELETE_ALL_PLUGIN_TEXT_RULES",
    "DELETE_ALL_PLUGIN_SOURCE_TEXT_RULES",
    "DELETE_ALL_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS",
    "DELETE_ALL_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE",
    "DELETE_ALL_SOURCE_SNAPSHOT_FILES",
    "DELETE_RULE_REVIEW_STATE",
    "DELETE_ALL_FIELD_TRANSLATION_TERMS",
    "DELETE_ALL_TEXT_GLOSSARY_TERMS",
    "DELETE_ALL_TEXT_INDEX_INVALIDATIONS",
    "DELETE_ALL_TEXT_INDEX_DOMAIN_SUMMARY",
    "DELETE_ALL_TEXT_INDEX_ITEMS",
    "DELETE_ALL_TEXT_INDEX_META",
    "DELETE_ALL_TEXT_INDEX_RULE_HIT_SUMMARY",
    "DELETE_ALL_TEXT_INDEX_SCOPE_SUMMARY",
    "DELETE_ALL_TRANSLATION_QUALITY_ERRORS",
    "DELETE_TRANSLATION_ITEM_BY_PATH",
    "DELETE_TRANSLATION_ITEMS_BY_PREFIX",
    "COUNT_PENDING_TEXT_INDEX_QUALITY_ERRORS",
    "COUNT_TEXT_INDEX_TRANSLATED_ITEMS",
    "COUNT_TRANSLATED_ITEMS",
    "COUNT_TRANSLATIONS_OUTSIDE_WRITABLE_TEXT_INDEX",
    "EVENT_COMMAND_TEXT_RULE_FILTERS_TABLE_NAME",
    "EVENT_COMMAND_TEXT_RULE_GROUPS_TABLE_NAME",
    "EVENT_COMMAND_TEXT_RULE_PATHS_TABLE_NAME",
    "EXPECTED_STATIC_TABLE_NAMES",
    "FONT_REPLACEMENT_RECORDS_TABLE_NAME",
    "FIELD_TRANSLATION_TERMS_TABLE_NAME",
    "INSERT_NONSTANDARD_DATA_TEXT_RULE",
    "INSERT_EVENT_COMMAND_TEXT_RULE_FILTER",
    "INSERT_EVENT_COMMAND_TEXT_RULE_GROUP",
    "INSERT_EVENT_COMMAND_TEXT_RULE_PATH",
    "INSERT_LLM_FAILURE",
    "INSERT_NOTE_TAG_TEXT_RULE",
    "INSERT_PLACEHOLDER_RULE",
    "INSERT_STRUCTURED_PLACEHOLDER_RULE",
    "INSERT_STRUCTURED_PLACEHOLDER_RULE_GROUP",
    "INSERT_SOURCE_RESIDUAL_RULE",
    "UPSERT_RULE_REVIEW_STATE",
    "INSERT_FONT_REPLACEMENT_RECORD",
    "INSERT_MV_VIRTUAL_NAMEBOX_RULE",
    "INSERT_PLUGIN_TEXT_RULE",
    "INSERT_PLUGIN_SOURCE_TEXT_RULE",
    "INSERT_PLUGIN_SOURCE_RUNTIME_WRITE_MAP",
    "INSERT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE",
    "INSERT_SOURCE_SNAPSHOT_FILE",
    "INSERT_TRANSLATION_QUALITY_ERROR",
    "INSERT_FIELD_TRANSLATION_TERM",
    "INSERT_TEXT_GLOSSARY_TERM",
    "INSERT_TEXT_INDEX_INVALIDATION",
    "INSERT_TEXT_INDEX_DOMAIN_SUMMARY",
    "INSERT_TEXT_INDEX_ITEM",
    "INSERT_TEXT_INDEX_RULE_HIT_SUMMARY",
    "UPSERT_TEXT_INDEX_SCOPE_SUMMARY",
    "LLM_FAILURES_TABLE_NAME",
    "LANGUAGE_SETTINGS_KEY",
    "LANGUAGE_SETTINGS_TABLE_NAME",
    "INSERT_TRANSLATION",
    "METADATA_KEY",
    "METADATA_TABLE_NAME",
    "MV_VIRTUAL_NAMEBOX_RULES_TABLE_NAME",
    "NONSTANDARD_DATA_TEXT_RULES_TABLE_NAME",
    "NOTE_TAG_TEXT_RULES_TABLE_NAME",
    "PLACEHOLDER_RULES_TABLE_NAME",
    "PLUGIN_TEXT_RULES_TABLE_NAME",
    "PLUGIN_SOURCE_TEXT_RULES_TABLE_NAME",
    "PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME",
    "PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME",
    "SOURCE_SNAPSHOT_FILES_TABLE_NAME",
    "RULE_REVIEW_STATES_TABLE_NAME",
    "SOURCE_RESIDUAL_RULES_TABLE_NAME",
    "STRUCTURED_PLACEHOLDER_RULE_GROUPS_TABLE_NAME",
    "STRUCTURED_PLACEHOLDER_RULES_TABLE_NAME",
    "SELECT_EVENT_COMMAND_TEXT_RULE_FILTERS",
    "SELECT_EVENT_COMMAND_TEXT_RULE_GROUPS",
    "SELECT_EVENT_COMMAND_TEXT_RULE_PATHS",
    "SELECT_METADATA",
    "SELECT_LANGUAGE_SETTINGS",
    "SELECT_NONSTANDARD_DATA_TEXT_RULES",
    "SELECT_NOTE_TAG_TEXT_RULES",
    "SELECT_LATEST_TRANSLATION_RUN",
    "SELECT_MV_VIRTUAL_NAMEBOX_RULES",
    "SELECT_SOURCE_RESIDUAL_RULES",
    "SELECT_FONT_REPLACEMENT_RECORDS",
    "SELECT_LLM_FAILURES_BY_RUN",
    "SELECT_PLACEHOLDER_RULES",
    "SELECT_STRUCTURED_PLACEHOLDER_RULE_GROUPS",
    "SELECT_STRUCTURED_PLACEHOLDER_RULES",
    "SELECT_PLUGIN_TEXT_RULES",
    "SELECT_PLUGIN_SOURCE_TEXT_RULES",
    "SELECT_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS",
    "SELECT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE",
    "SELECT_SOURCE_SNAPSHOT_FILES",
    "SELECT_RULE_REVIEW_STATE",
    "COUNT_TRANSLATION_QUALITY_ERRORS_BY_RUN",
    "SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_TYPE_COUNTS",
    "SELECT_TRANSLATION_QUALITY_ERROR_TYPE_COUNTS_BY_RUN",
    "SELECT_TRANSLATION_QUALITY_ERROR_BY_RUN_AND_PATH",
    "SELECT_TRANSLATION_QUALITY_ERRORS_BY_RUN",
    "SELECT_TRANSLATION_RUN",
    "SELECT_TRANSLATED_ITEMS",
    "SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX",
    "SELECT_TRANSLATED_ITEMS_BY_PREFIX",
    "SELECT_TRANSLATED_ITEM_BY_PATH",
    "SELECT_TRANSLATION_PATHS",
    "SELECT_SCHEMA_VERSION",
    "SELECT_TABLE_NAMES",
    "SELECT_TERMINOLOGY_BUNDLE_STATE",
    "SELECT_TEXT_GLOSSARY_TERMS",
    "SELECT_PENDING_TEXT_INDEX_COUNT",
    "SELECT_PENDING_TEXT_INDEX_ITEMS",
    "SELECT_TEXT_INDEX_INVALIDATIONS",
    "SELECT_TEXT_INDEX_DOMAIN_SUMMARY",
    "SELECT_TEXT_INDEX_ITEM_COUNT",
    "SELECT_TEXT_INDEX_ITEMS",
    "SELECT_TEXT_INDEX_ITEM_BY_PATH",
    "SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS",
    "SELECT_TEXT_INDEX_LOCATION_PATHS",
    "SELECT_WRITABLE_TEXT_INDEX_LOCATION_PATHS",
    "SELECT_TEXT_INDEX_META",
    "SELECT_TEXT_INDEX_RULE_HIT_SUMMARY",
    "SELECT_TEXT_INDEX_SCOPE_SUMMARY",
    "SELECT_FIELD_TRANSLATION_TERMS",
    "SCHEMA_VERSION_KEY",
    "SCHEMA_VERSION_TABLE_NAME",
    "TEXT_GLOSSARY_TERMS_TABLE_NAME",
    "TEXT_INDEX_INVALIDATIONS_TABLE_NAME",
    "TEXT_INDEX_DOMAIN_SUMMARY_TABLE_NAME",
    "TEXT_INDEX_ITEMS_TABLE_NAME",
    "TEXT_INDEX_META_KEY",
    "TEXT_INDEX_META_TABLE_NAME",
    "TEXT_INDEX_RULE_HIT_SUMMARY_TABLE_NAME",
    "TEXT_INDEX_SCOPE_SUMMARY_TABLE_NAME",
    "TERMINOLOGY_BUNDLE_STATE_KEY",
    "TERMINOLOGY_BUNDLE_STATE_TABLE_NAME",
    "TRANSLATION_QUALITY_ERRORS_TABLE_NAME",
    "TRANSLATION_RUNS_TABLE_NAME",
    "TRANSLATION_TABLE_NAME",
    "UPSERT_METADATA",
    "UPSERT_LANGUAGE_SETTINGS",
    "UPSERT_SCHEMA_VERSION",
    "UPSERT_TERMINOLOGY_BUNDLE_STATE",
    "UPSERT_TEXT_INDEX_META",
    "UPSERT_TRANSLATION_RUN",
    "CURRENT_SCHEMA_VERSION",
]
