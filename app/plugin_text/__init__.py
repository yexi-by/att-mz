"""插件文本翻译模块导出入口。"""

from .common import (
    build_json_string_leaf_path_hint,
    build_plugin_hash,
    build_plugins_file_hash,
    collect_plugin_json_string_leaf_candidates,
    expand_rule_to_leaf_paths,
    extract_plugin_name,
    resolve_plugin_leaves,
)
from .extraction import PluginTextExtraction
from .exporter import export_plugins_json_file
from .importer import (
    PluginRuleImportFile,
    PluginRuleSpec,
    build_plugin_rule_records_from_import,
    load_plugin_rule_import_file,
    parse_plugin_rule_import_text,
)
from .native_validation import (
    NativePluginRuleValidationContext,
    build_native_plugin_rule_validation_context,
    build_native_plugin_rule_validation_context_from_import,
)

__all__: list[str] = [
    "NativePluginRuleValidationContext",
    "PluginRuleImportFile",
    "PluginRuleSpec",
    "PluginTextExtraction",
    "build_native_plugin_rule_validation_context",
    "build_native_plugin_rule_validation_context_from_import",
    "build_json_string_leaf_path_hint",
    "build_plugin_hash",
    "build_plugin_rule_records_from_import",
    "build_plugins_file_hash",
    "collect_plugin_json_string_leaf_candidates",
    "export_plugins_json_file",
    "expand_rule_to_leaf_paths",
    "extract_plugin_name",
    "load_plugin_rule_import_file",
    "parse_plugin_rule_import_text",
    "resolve_plugin_leaves",
]
