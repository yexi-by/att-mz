-- ATT-MZ SQLite schema v20. Shared by Python persistence and Rust native storage.
-- Keep schema_version value in app.persistence.sql.CURRENT_SCHEMA_VERSION.

--sql
    CREATE TABLE IF NOT EXISTS [schema_version] (
        schema_key TEXT PRIMARY KEY,
        version    INTEGER NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [translation_items] (
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

--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_location_path]
    ON [translation_items](location_path)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_source_fact_raw_hash]
    ON [translation_items](source_fact_raw_hash)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_items_source_fact_translatable_hash]
    ON [translation_items](source_fact_translatable_hash)
;

--sql
    CREATE TABLE IF NOT EXISTS [metadata] (
        metadata_key TEXT PRIMARY KEY,
        game_title   TEXT NOT NULL,
        game_path    TEXT NOT NULL,
        engine_kind  TEXT NOT NULL,
        content_root TEXT NOT NULL,
        engine_version TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [language_settings] (
        settings_key    TEXT PRIMARY KEY,
        source_language TEXT NOT NULL,
        target_language TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [plugin_source_runtime_write_map] (
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

--sql
    CREATE TABLE IF NOT EXISTS [plugin_source_runtime_scan_cache] (
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

--sql
    CREATE TABLE IF NOT EXISTS [source_snapshot_files] (
        relative_path TEXT PRIMARY KEY,
        sha256        TEXT NOT NULL,
        byte_size     INTEGER NOT NULL,
        updated_at    TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [terminology_field_terms] (
        category        TEXT NOT NULL,
        source_text     TEXT NOT NULL,
        translated_text TEXT NOT NULL,
        PRIMARY KEY (category, source_text)
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_glossary_terms] (
        source_text     TEXT PRIMARY KEY,
        translated_text TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [terminology_bundle_state] (
        state_key TEXT PRIMARY KEY,
        imported  INTEGER NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [rule_sets] (
        domain TEXT PRIMARY KEY,
        source_kind TEXT NOT NULL,
        rule_count INTEGER NOT NULL,
        context_hash TEXT NOT NULL,
        rules_hash TEXT NOT NULL,
        rule_runtime_contract_version INTEGER NOT NULL,
        rule_store_schema_version INTEGER NOT NULL,
        imported_at TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [rules] (
        rule_id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        rule_order INTEGER NOT NULL,
        matcher_kind TEXT NOT NULL,
        matcher_value TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        source_kind TEXT NOT NULL,
        rule_hash TEXT NOT NULL,
        UNIQUE(domain, rule_order, rule_id)
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [rule_domain_states] (
        domain TEXT PRIMARY KEY,
        state_json TEXT NOT NULL,
        scope_hash TEXT NOT NULL,
        confirmed_at TEXT NOT NULL,
        rule_runtime_contract_version INTEGER NOT NULL,
        rule_store_schema_version INTEGER NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [font_replacement_records] (
        file_name             TEXT NOT NULL,
        value_path            TEXT NOT NULL,
        original_text         TEXT NOT NULL,
        replaced_text         TEXT NOT NULL,
        replacement_font_name TEXT NOT NULL,
        PRIMARY KEY (file_name, value_path)
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [translation_runs] (
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

--sql
    CREATE TABLE IF NOT EXISTS [llm_failures] (
        failure_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          TEXT NOT NULL,
        category        TEXT NOT NULL,
        error_type      TEXT NOT NULL,
        error_message   TEXT NOT NULL,
        retryable       INTEGER NOT NULL,
        attempt_count   INTEGER NOT NULL,
        created_at      TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES [translation_runs](run_id) ON DELETE CASCADE
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [translation_quality_errors] (
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
        FOREIGN KEY (run_id) REFERENCES [translation_runs](run_id) ON DELETE CASCADE
    )
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_translation_quality_errors_fact_id]
    ON [translation_quality_errors](fact_id)
;

--sql
    CREATE TABLE IF NOT EXISTS [text_index_meta] (
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

--sql
    CREATE TABLE IF NOT EXISTS [text_index_items] (
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

--sql
    CREATE TABLE IF NOT EXISTS [text_index_scope_summary] (
        index_key           TEXT PRIMARY KEY,
        total_count         INTEGER NOT NULL,
        active_count        INTEGER NOT NULL,
        writable_count      INTEGER NOT NULL,
        unwritable_count    INTEGER NOT NULL,
        stale_rule_count    INTEGER NOT NULL,
        native_thread_count INTEGER NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_index_domain_summary] (
        domain                  TEXT PRIMARY KEY,
        item_count              INTEGER NOT NULL,
        active_count            INTEGER NOT NULL,
        writable_count          INTEGER NOT NULL,
        unwritable_count        INTEGER NOT NULL,
        inactive_rule_hit_count INTEGER NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_index_rule_hit_summary] (
        domain            TEXT NOT NULL,
        rule_key          TEXT NOT NULL,
        hit_count         INTEGER NOT NULL,
        extractable_count INTEGER NOT NULL,
        writable_count    INTEGER NOT NULL,
        unwritable_count  INTEGER NOT NULL,
        PRIMARY KEY (domain, rule_key)
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_index_invalidations] (
        reason_key TEXT PRIMARY KEY,
        detail     TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_facts] (
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

--sql
    CREATE TABLE IF NOT EXISTS [text_fact_render_parts] (
        fact_id       TEXT NOT NULL,
        part_order    INTEGER NOT NULL,
        part_kind     TEXT NOT NULL,
        raw_text      TEXT NOT NULL,
        semantic_text TEXT NOT NULL,
        template_key  TEXT NOT NULL,
        PRIMARY KEY (fact_id, part_order),
        FOREIGN KEY (fact_id) REFERENCES [text_facts](fact_id) ON DELETE CASCADE
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_fact_domain_payloads] (
        fact_id      TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (fact_id) REFERENCES [text_facts](fact_id) ON DELETE CASCADE
    )
;

--sql
    CREATE TABLE IF NOT EXISTS [text_fact_scope] (
        scope_key            TEXT PRIMARY KEY,
        schema_version       INTEGER NOT NULL,
        scope_hash           TEXT NOT NULL,
        source_snapshot_hash TEXT NOT NULL,
        rule_hash            TEXT NOT NULL,
        text_rules_hash      TEXT NOT NULL,
        created_at           TEXT NOT NULL
    )
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_domain_location]
    ON [text_facts](domain, location_path)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_domain_source_file]
    ON [text_facts](domain, source_file)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_selector]
    ON [text_facts](selector)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_visible_hash]
    ON [text_facts](visible_hash)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_translatable_hash]
    ON [text_facts](translatable_hash)
;

--sql
    CREATE INDEX IF NOT EXISTS [idx_text_facts_scope_key]
    ON [text_facts](scope_key)
;

INSERT OR REPLACE INTO [schema_version] (schema_key, version)
VALUES ('current', 20)
;
