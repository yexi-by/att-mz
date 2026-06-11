"""多游戏数据库管理器使用的 SQL 语句模块。"""

from __future__ import annotations

import hashlib
from importlib import resources

TRANSLATION_TABLE_NAME = "translation_items"
METADATA_TABLE_NAME = "metadata"
LANGUAGE_SETTINGS_TABLE_NAME = "language_settings"
SCHEMA_VERSION_TABLE_NAME = "schema_version"
PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME = "plugin_source_runtime_write_map"
PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME = "plugin_source_runtime_scan_cache"
SOURCE_SNAPSHOT_FILES_TABLE_NAME = "source_snapshot_files"
FIELD_TRANSLATION_TERMS_TABLE_NAME = "terminology_field_terms"
TEXT_GLOSSARY_TERMS_TABLE_NAME = "text_glossary_terms"
TERMINOLOGY_BUNDLE_STATE_TABLE_NAME = "terminology_bundle_state"
RULE_SETS_TABLE_NAME = "rule_sets"
RULES_TABLE_NAME = "rules"
RULE_DOMAIN_STATES_TABLE_NAME = "rule_domain_states"
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
TEXT_FACTS_TABLE_NAME = "text_facts"
TEXT_FACT_RENDER_PARTS_TABLE_NAME = "text_fact_render_parts"
TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME = "text_fact_domain_payloads"
TEXT_FACT_SCOPE_TABLE_NAME = "text_fact_scope"
METADATA_KEY = "current_game"
LANGUAGE_SETTINGS_KEY = "current"
SCHEMA_VERSION_KEY = "current"
TEXT_INDEX_META_KEY = "current"
CURRENT_SCHEMA_VERSION = 20
CURRENT_TEXT_FACT_CONTRACT_VERSION = 2
CURRENT_SCHEMA_RESOURCE_PACKAGE = "app.persistence.schema"
CURRENT_SCHEMA_RESOURCE_NAME = "current.sql"
TERMINOLOGY_BUNDLE_STATE_KEY = "current"
EXPECTED_STATIC_TABLE_NAMES: tuple[str, ...] = (
    SCHEMA_VERSION_TABLE_NAME,
    TRANSLATION_TABLE_NAME,
    METADATA_TABLE_NAME,
    LANGUAGE_SETTINGS_TABLE_NAME,
    PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME,
    PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME,
    SOURCE_SNAPSHOT_FILES_TABLE_NAME,
    FIELD_TRANSLATION_TERMS_TABLE_NAME,
    TEXT_GLOSSARY_TERMS_TABLE_NAME,
    TERMINOLOGY_BUNDLE_STATE_TABLE_NAME,
    RULE_SETS_TABLE_NAME,
    RULES_TABLE_NAME,
    RULE_DOMAIN_STATES_TABLE_NAME,
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
    TEXT_FACTS_TABLE_NAME,
    TEXT_FACT_RENDER_PARTS_TABLE_NAME,
    TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME,
    TEXT_FACT_SCOPE_TABLE_NAME,
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
        fact_id                       TEXT PRIMARY KEY,
        location_path                 TEXT NOT NULL,
        item_type                     TEXT NOT NULL,
        role                          TEXT,
        original_lines                TEXT NOT NULL,
        source_line_paths             TEXT NOT NULL,
        source_fact_raw_hash          TEXT NOT NULL,
        source_fact_translatable_hash TEXT NOT NULL,
        translation_lines             TEXT NOT NULL
    )
;
"""

CREATE_TRANSLATION_LOCATION_PATH_INDEX = f"""
--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_location_path]
    ON [{TRANSLATION_TABLE_NAME}](location_path)
;
"""

CREATE_TRANSLATION_SOURCE_FACT_RAW_HASH_INDEX = f"""
--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_source_fact_raw_hash]
    ON [{TRANSLATION_TABLE_NAME}](source_fact_raw_hash)
;
"""

CREATE_TRANSLATION_SOURCE_FACT_TRANSLATABLE_HASH_INDEX = f"""
--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_source_fact_translatable_hash]
    ON [{TRANSLATION_TABLE_NAME}](source_fact_translatable_hash)
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
        fact_id          TEXT NOT NULL,
        location_path    TEXT NOT NULL,
        item_type        TEXT NOT NULL,
        role             TEXT,
        original_lines   TEXT NOT NULL,
        translation_lines TEXT NOT NULL,
        error_type       TEXT NOT NULL,
        error_detail     TEXT NOT NULL,
        model_response   TEXT NOT NULL,
        PRIMARY KEY (run_id, fact_id, location_path),
        FOREIGN KEY (run_id) REFERENCES [{TRANSLATION_RUNS_TABLE_NAME}](run_id) ON DELETE CASCADE
    )
;
"""

CREATE_TRANSLATION_QUALITY_ERRORS_FACT_ID_INDEX = f"""
--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_quality_errors_fact_id]
    ON [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}](fact_id)
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
        workflow_gate_facts         TEXT NOT NULL,
        rust_contract_version       INTEGER NOT NULL,
        parser_contract_version     INTEGER NOT NULL,
        source_branch_contract_version INTEGER NOT NULL,
        text_fact_schema_version    INTEGER NOT NULL,
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

CREATE_TEXT_FACTS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_FACTS_TABLE_NAME}] (
        fact_id            TEXT PRIMARY KEY,
        schema_version     INTEGER NOT NULL,
        domain             TEXT NOT NULL,
        location_path      TEXT NOT NULL,
        source_file        TEXT NOT NULL,
        source_type        TEXT NOT NULL,
        item_type          TEXT NOT NULL,
        role               TEXT NOT NULL,
        selector           TEXT NOT NULL,
        raw_text           TEXT NOT NULL,
        visible_text       TEXT NOT NULL,
        translatable_text  TEXT NOT NULL,
        raw_hash           TEXT NOT NULL,
        visible_hash       TEXT NOT NULL,
        translatable_hash  TEXT NOT NULL,
        scope_key          TEXT NOT NULL
    )
;
"""

CREATE_TEXT_FACT_RENDER_PARTS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_FACT_RENDER_PARTS_TABLE_NAME}] (
        fact_id       TEXT NOT NULL,
        part_order    INTEGER NOT NULL,
        part_kind     TEXT NOT NULL,
        raw_text      TEXT NOT NULL,
        semantic_text TEXT NOT NULL,
        template_key  TEXT NOT NULL,
        PRIMARY KEY (fact_id, part_order),
        FOREIGN KEY (fact_id) REFERENCES [{TEXT_FACTS_TABLE_NAME}](fact_id) ON DELETE CASCADE
    )
;
"""

CREATE_TEXT_FACT_DOMAIN_PAYLOADS_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME}] (
        fact_id      TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (fact_id) REFERENCES [{TEXT_FACTS_TABLE_NAME}](fact_id) ON DELETE CASCADE
    )
;
"""

CREATE_TEXT_FACT_SCOPE_TABLE = f"""
--sql
    CREATE TABLE IF NOT EXISTS [{TEXT_FACT_SCOPE_TABLE_NAME}] (
        scope_key            TEXT PRIMARY KEY,
        schema_version       INTEGER NOT NULL,
        scope_hash           TEXT NOT NULL,
        source_snapshot_hash TEXT NOT NULL,
        rule_hash            TEXT NOT NULL,
        text_rules_hash      TEXT NOT NULL,
        created_at           TEXT NOT NULL
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
        rust_contract_version INTEGER NOT NULL,
        parser_contract_version INTEGER NOT NULL,
        audit_contract_version INTEGER NOT NULL,
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
    (
        fact_id,
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_fact_raw_hash,
        source_fact_translatable_hash,
        translation_lines
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

UPSERT_RULE_REVIEW_STATE = f"""
--sql
    INSERT OR REPLACE INTO [{RULE_DOMAIN_STATES_TABLE_NAME}]
    (domain, state_json, scope_hash, confirmed_at, rule_runtime_contract_version, rule_store_schema_version)
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

UPSERT_RULE_SET = f"""
--sql
    INSERT OR REPLACE INTO [{RULE_SETS_TABLE_NAME}]
    (domain, source_kind, rule_count, context_hash, rules_hash, rule_runtime_contract_version, rule_store_schema_version, imported_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_RULE = f"""
--sql
    INSERT INTO [{RULES_TABLE_NAME}]
    (rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    (
        run_id,
        fact_id,
        location_path,
        item_type,
        role,
        original_lines,
        translation_lines,
        error_type,
        error_detail,
        model_response
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

UPSERT_TEXT_INDEX_META = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_INDEX_META_TABLE_NAME}]
    (
        index_key,
        source_snapshot_fingerprint,
        rules_fingerprint,
        item_count,
        workflow_gate_scope_hashes,
        workflow_gate_facts,
        rust_contract_version,
        parser_contract_version,
        source_branch_contract_version,
        text_fact_schema_version,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

UPDATE_TEXT_INDEX_WORKFLOW_GATE_SCOPE_HASHES = f"""
--sql
    UPDATE [{TEXT_INDEX_META_TABLE_NAME}]
    SET workflow_gate_scope_hashes = ?
    WHERE index_key = ?
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

INSERT_TEXT_FACT_SCOPE = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_FACT_SCOPE_TABLE_NAME}]
    (
        scope_key,
        schema_version,
        scope_hash,
        source_snapshot_hash,
        rule_hash,
        text_rules_hash,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_FACT = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_FACTS_TABLE_NAME}]
    (
        fact_id,
        schema_version,
        domain,
        location_path,
        source_file,
        source_type,
        item_type,
        role,
        selector,
        raw_text,
        visible_text,
        translatable_text,
        raw_hash,
        visible_hash,
        translatable_hash,
        scope_key
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_FACT_RENDER_PART = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_FACT_RENDER_PARTS_TABLE_NAME}]
    (fact_id, part_order, part_kind, raw_text, semantic_text, template_key)
    VALUES (?, ?, ?, ?, ?, ?)
;
"""

INSERT_TEXT_FACT_DOMAIN_PAYLOAD = f"""
--sql
    INSERT OR REPLACE INTO [{TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME}]
    (fact_id, payload_json)
    VALUES (?, ?)
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

DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS = f"""
--sql
    DELETE FROM [{TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_FACT_RENDER_PARTS = f"""
--sql
    DELETE FROM [{TEXT_FACT_RENDER_PARTS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_FACTS = f"""
--sql
    DELETE FROM [{TEXT_FACTS_TABLE_NAME}]
;
"""

DELETE_ALL_TEXT_FACT_SCOPES = f"""
--sql
    DELETE FROM [{TEXT_FACT_SCOPE_TABLE_NAME}]
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
    SELECT
        fact_id,
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_fact_raw_hash,
        source_fact_translatable_hash,
        translation_lines
    FROM [{TRANSLATION_TABLE_NAME}]
    ORDER BY location_path
;
"""

SELECT_TRANSLATED_ITEMS_BY_PREFIX = f"""
--sql
    SELECT
        fact_id,
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_fact_raw_hash,
        source_fact_translatable_hash,
        translation_lines
    FROM [{TRANSLATION_TABLE_NAME}]
    WHERE location_path LIKE ?
    ORDER BY location_path
;
"""

SELECT_TRANSLATED_ITEM_BY_PATH = f"""
--sql
    SELECT
        fact_id,
        location_path,
        item_type,
        role,
        original_lines,
        source_line_paths,
        source_fact_raw_hash,
        source_fact_translatable_hash,
        translation_lines
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

SELECT_RULE_REVIEW_STATE = f"""
--sql
    SELECT domain, state_json, scope_hash, confirmed_at
    FROM [{RULE_DOMAIN_STATES_TABLE_NAME}]
    WHERE domain = ?
    LIMIT 1
;
"""

SELECT_RULES_BY_DOMAIN = f"""
--sql
    SELECT rule_id, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash
    FROM [{RULES_TABLE_NAME}]
    WHERE domain = ?
    ORDER BY rule_order, rule_id
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
    SELECT
        source_snapshot_fingerprint,
        rules_fingerprint,
        item_count,
        workflow_gate_scope_hashes,
        workflow_gate_facts,
        rust_contract_version,
        parser_contract_version,
        source_branch_contract_version,
        text_fact_schema_version,
        created_at
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

SELECT_TEXT_INDEX_PLACEHOLDER_TEXTS = f"""
--sql
    SELECT
        location_path,
        original_lines
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

SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_PATHS = f"""
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

SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX = f"""
--sql
    SELECT
        translations.fact_id,
        translations.location_path,
        translations.item_type,
        translations.role,
        translations.original_lines,
        translations.source_line_paths,
        translations.source_fact_raw_hash,
        translations.source_fact_translatable_hash,
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

SELECT_TEXT_FACT_SCOPE = f"""
--sql
    SELECT
        scope_key,
        schema_version,
        scope_hash,
        source_snapshot_hash,
        rule_hash,
        text_rules_hash,
        created_at
    FROM [{TEXT_FACT_SCOPE_TABLE_NAME}]
    WHERE scope_key = ?
    LIMIT 1
;
"""

COUNT_TEXT_FACTS = f"""
--sql
    SELECT COUNT(*) AS fact_count
    FROM [{TEXT_FACTS_TABLE_NAME}]
;
"""

COUNT_TEXT_FACTS_OUTSIDE_SCOPE = f"""
--sql
    SELECT COUNT(*) AS mismatch_count
    FROM [{TEXT_FACTS_TABLE_NAME}]
    WHERE scope_key <> ?
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
    (
        file_name,
        file_hash,
        rust_contract_version,
        parser_contract_version,
        audit_contract_version,
        syntax_error,
        literals_json,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
;
"""

SELECT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE = f"""
--sql
    SELECT
        file_name,
        file_hash,
        rust_contract_version,
        parser_contract_version,
        audit_contract_version,
        syntax_error,
        literals_json,
        created_at
    FROM [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}]
    ORDER BY file_name
;
"""

DELETE_ALL_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE = f"""
--sql
    DELETE FROM [{PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME}]
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

DELETE_RULE_REVIEW_STATE = f"""
--sql
    DELETE FROM [{RULE_DOMAIN_STATES_TABLE_NAME}]
    WHERE domain = ?
;
"""

DELETE_RULES_BY_DOMAIN = f"""
--sql
    DELETE FROM [{RULES_TABLE_NAME}]
    WHERE domain = ?
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

CHECK_CONNECTION_READABLE = """
--sql
    SELECT 1
;
"""


def current_schema_sql() -> str:
    """读取 Python 建库和 Rust native 共用的当前 SQLite schema SQL。"""
    return resources.files(CURRENT_SCHEMA_RESOURCE_PACKAGE).joinpath(CURRENT_SCHEMA_RESOURCE_NAME).read_text(
        encoding="utf-8",
    )


def current_schema_fingerprint() -> str:
    """返回共享 schema SQL 的稳定 SHA-256 指纹。"""
    return hashlib.sha256(current_schema_sql().encode("utf-8")).hexdigest()

__all__: list[str] = [
    "CHECK_CONNECTION_READABLE",
    "CREATE_SCHEMA_VERSION_TABLE",
    "CREATE_FONT_REPLACEMENT_RECORDS_TABLE",
    "CREATE_LLM_FAILURES_TABLE",
    "CREATE_LANGUAGE_SETTINGS_TABLE",
    "CREATE_METADATA_TABLE",
    "CREATE_PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE",
    "CREATE_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE",
    "CREATE_SOURCE_SNAPSHOT_FILES_TABLE",
    "CREATE_TRANSLATION_QUALITY_ERRORS_TABLE",
    "CREATE_TRANSLATION_RUNS_TABLE",
    "CREATE_TRANSLATION_TABLE",
    "CREATE_TEXT_INDEX_INVALIDATIONS_TABLE",
    "CREATE_TEXT_INDEX_DOMAIN_SUMMARY_TABLE",
    "CREATE_TEXT_INDEX_ITEMS_TABLE",
    "CREATE_TEXT_INDEX_META_TABLE",
    "CREATE_TEXT_INDEX_RULE_HIT_SUMMARY_TABLE",
    "CREATE_TEXT_INDEX_SCOPE_SUMMARY_TABLE",
    "CREATE_TEXT_FACT_DOMAIN_PAYLOADS_TABLE",
    "CREATE_TEXT_FACT_RENDER_PARTS_TABLE",
    "CREATE_TEXT_FACT_SCOPE_TABLE",
    "CREATE_TEXT_FACTS_TABLE",
    "CREATE_TERMINOLOGY_BUNDLE_STATE_TABLE",
    "CREATE_FIELD_TRANSLATION_TERMS_TABLE",
    "CREATE_TEXT_GLOSSARY_TERMS_TABLE",
    "DELETE_ALL_FONT_REPLACEMENT_RECORDS",
    "DELETE_ALL_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS",
    "DELETE_ALL_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE",
    "DELETE_ALL_SOURCE_SNAPSHOT_FILES",
    "DELETE_RULE_REVIEW_STATE",
    "DELETE_RULES_BY_DOMAIN",
    "DELETE_ALL_FIELD_TRANSLATION_TERMS",
    "DELETE_ALL_TEXT_GLOSSARY_TERMS",
    "DELETE_ALL_TEXT_INDEX_INVALIDATIONS",
    "DELETE_ALL_TEXT_INDEX_DOMAIN_SUMMARY",
    "DELETE_ALL_TEXT_INDEX_ITEMS",
    "DELETE_ALL_TEXT_INDEX_META",
    "DELETE_ALL_TEXT_INDEX_RULE_HIT_SUMMARY",
    "DELETE_ALL_TEXT_INDEX_SCOPE_SUMMARY",
    "DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS",
    "DELETE_ALL_TEXT_FACT_RENDER_PARTS",
    "DELETE_ALL_TEXT_FACT_SCOPES",
    "DELETE_ALL_TEXT_FACTS",
    "DELETE_ALL_TRANSLATION_QUALITY_ERRORS",
    "DELETE_TRANSLATION_ITEMS_BY_PREFIX",
    "COUNT_PENDING_TEXT_INDEX_QUALITY_ERRORS",
    "COUNT_TEXT_FACTS",
    "COUNT_TEXT_FACTS_OUTSIDE_SCOPE",
    "COUNT_TEXT_INDEX_TRANSLATED_ITEMS",
    "COUNT_TRANSLATED_ITEMS",
    "EXPECTED_STATIC_TABLE_NAMES",
    "FONT_REPLACEMENT_RECORDS_TABLE_NAME",
    "FIELD_TRANSLATION_TERMS_TABLE_NAME",
    "INSERT_LLM_FAILURE",
    "UPSERT_RULE_REVIEW_STATE",
    "UPSERT_RULE_SET",
    "INSERT_RULE",
    "INSERT_FONT_REPLACEMENT_RECORD",
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
    "INSERT_TEXT_FACT_DOMAIN_PAYLOAD",
    "INSERT_TEXT_FACT_RENDER_PART",
    "INSERT_TEXT_FACT_SCOPE",
    "INSERT_TEXT_FACT",
    "UPSERT_TEXT_INDEX_SCOPE_SUMMARY",
    "LLM_FAILURES_TABLE_NAME",
    "LANGUAGE_SETTINGS_KEY",
    "LANGUAGE_SETTINGS_TABLE_NAME",
    "INSERT_TRANSLATION",
    "METADATA_KEY",
    "METADATA_TABLE_NAME",
    "PLUGIN_SOURCE_RUNTIME_WRITE_MAP_TABLE_NAME",
    "PLUGIN_SOURCE_RUNTIME_SCAN_CACHE_TABLE_NAME",
    "SOURCE_SNAPSHOT_FILES_TABLE_NAME",
    "RULE_DOMAIN_STATES_TABLE_NAME",
    "RULE_SETS_TABLE_NAME",
    "RULES_TABLE_NAME",
    "TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME",
    "TEXT_FACT_RENDER_PARTS_TABLE_NAME",
    "TEXT_FACT_SCOPE_TABLE_NAME",
    "TEXT_FACTS_TABLE_NAME",
    "SELECT_METADATA",
    "SELECT_LANGUAGE_SETTINGS",
    "SELECT_LATEST_TRANSLATION_RUN",
    "SELECT_FONT_REPLACEMENT_RECORDS",
    "SELECT_LLM_FAILURES_BY_RUN",
    "SELECT_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS",
    "SELECT_PLUGIN_SOURCE_RUNTIME_SCAN_CACHE",
    "SELECT_SOURCE_SNAPSHOT_FILES",
    "SELECT_RULE_REVIEW_STATE",
    "SELECT_RULES_BY_DOMAIN",
    "COUNT_TRANSLATION_QUALITY_ERRORS_BY_RUN",
    "SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_TYPE_COUNTS",
    "SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_PATHS",
    "SELECT_TRANSLATION_QUALITY_ERROR_TYPE_COUNTS_BY_RUN",
    "SELECT_TRANSLATION_QUALITY_ERROR_BY_RUN_AND_PATH",
    "SELECT_TRANSLATION_QUALITY_ERRORS_BY_RUN",
    "SELECT_TRANSLATION_RUN",
    "SELECT_TRANSLATED_ITEMS",
    "SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX",
    "SELECT_TRANSLATED_ITEMS_BY_PREFIX",
    "SELECT_TRANSLATED_ITEM_BY_PATH",
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
    "SELECT_TEXT_INDEX_PLACEHOLDER_TEXTS",
    "SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS",
    "SELECT_TEXT_INDEX_LOCATION_PATHS",
    "SELECT_WRITABLE_TEXT_INDEX_LOCATION_PATHS",
    "SELECT_TEXT_INDEX_META",
    "SELECT_TEXT_INDEX_RULE_HIT_SUMMARY",
    "SELECT_TEXT_INDEX_SCOPE_SUMMARY",
    "SELECT_TEXT_FACT_SCOPE",
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
    "UPDATE_TEXT_INDEX_WORKFLOW_GATE_SCOPE_HASHES",
    "UPSERT_TRANSLATION_RUN",
    "CURRENT_SCHEMA_VERSION",
    "CURRENT_TEXT_FACT_CONTRACT_VERSION",
    "CURRENT_SCHEMA_RESOURCE_NAME",
    "CURRENT_SCHEMA_RESOURCE_PACKAGE",
    "current_schema_fingerprint",
    "current_schema_sql",
]
