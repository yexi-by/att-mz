"""插件源码文本 AST 支线能力。"""

from .extraction import (
    PluginSourceTextExtraction,
    parse_plugin_source_location_path,
    plugin_source_file_key,
    plugin_source_location_path,
)
from .importer import (
    build_plugin_source_rule_records_from_import,
    parse_plugin_source_rule_import_text,
    plugin_source_rule_records_to_import_json,
)
from .models import (
    PluginSourceCandidate,
    PluginSourceFileScan,
    PluginSourceRisk,
    PluginSourceRuleImportEntry,
    PluginSourceRuleImportFile,
    PluginSourceScan,
)
from .native_scan import (
    build_native_plugin_source_scan,
)
from .rules import (
    PluginSourceReviewCoverage,
    StalePluginSourceTextRule,
    collect_plugin_source_review_coverage,
    filter_fresh_plugin_source_text_rules,
)
from .runtime_audit import (
    ActiveRuntimePluginSourceAudit,
    ActiveRuntimePluginSourceIssue,
    ActiveRuntimePluginSourceScanCacheStats,
    audit_active_runtime_plugin_source,
    audit_active_runtime_plugin_source_with_scan_cache,
    scan_plugin_source_files_text_strict_with_cache,
)
from .runtime_mapping import (
    plugin_source_runtime_hash_lines,
    plugin_source_runtime_hash_text,
)
__all__ = [
    "PluginSourceCandidate",
    "PluginSourceFileScan",
    "PluginSourceRisk",
    "PluginSourceRuleImportEntry",
    "PluginSourceRuleImportFile",
    "PluginSourceScan",
    "PluginSourceTextExtraction",
    "PluginSourceReviewCoverage",
    "StalePluginSourceTextRule",
    "ActiveRuntimePluginSourceAudit",
    "ActiveRuntimePluginSourceIssue",
    "ActiveRuntimePluginSourceScanCacheStats",
    "audit_active_runtime_plugin_source",
    "audit_active_runtime_plugin_source_with_scan_cache",
    "scan_plugin_source_files_text_strict_with_cache",
    "build_plugin_source_rule_records_from_import",
    "build_native_plugin_source_scan",
    "collect_plugin_source_review_coverage",
    "filter_fresh_plugin_source_text_rules",
    "parse_plugin_source_location_path",
    "parse_plugin_source_rule_import_text",
    "plugin_source_file_key",
    "plugin_source_location_path",
    "plugin_source_runtime_hash_lines",
    "plugin_source_runtime_hash_text",
    "plugin_source_rule_records_to_import_json",
]
