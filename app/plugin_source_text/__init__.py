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
from .rules import (
    PluginSourceReviewCoverage,
    StalePluginSourceTextRule,
    collect_plugin_source_review_coverage,
    filter_fresh_plugin_source_text_rules,
)
from .scanner import (
    PluginSourceCandidateIndex,
    build_plugin_source_candidate_index,
    build_plugin_source_file_hash,
    build_plugin_source_scan,
    find_candidate_by_selector,
)

__all__ = [
    "PluginSourceCandidate",
    "PluginSourceCandidateIndex",
    "PluginSourceFileScan",
    "PluginSourceRisk",
    "PluginSourceRuleImportEntry",
    "PluginSourceRuleImportFile",
    "PluginSourceScan",
    "PluginSourceTextExtraction",
    "PluginSourceReviewCoverage",
    "StalePluginSourceTextRule",
    "build_plugin_source_candidate_index",
    "build_plugin_source_file_hash",
    "build_plugin_source_rule_records_from_import",
    "build_plugin_source_scan",
    "collect_plugin_source_review_coverage",
    "filter_fresh_plugin_source_text_rules",
    "find_candidate_by_selector",
    "parse_plugin_source_location_path",
    "parse_plugin_source_rule_import_text",
    "plugin_source_file_key",
    "plugin_source_location_path",
    "plugin_source_rule_records_to_import_json",
]
