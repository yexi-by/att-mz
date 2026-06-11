//! Python 扩展入口。
//!
//! 本模块只暴露 PyO3 绑定，CPU 密集型规则计算集中放在 `native_core`。

mod native_core;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const NATIVE_CONTRACT_VERSION: usize = 14;

#[pyfunction]
fn native_contract_version() -> usize {
    NATIVE_CONTRACT_VERSION
}

#[pyfunction]
fn native_thread_count() -> PyResult<usize> {
    native_core::read_configured_thread_count()
        .map(|thread_count| thread_count.unwrap_or_else(rayon::current_num_threads))
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn configure_runtime_threads(rust_threads: Option<usize>) -> PyResult<()> {
    native_core::configure_runtime_threads(rust_threads).map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_quality(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_quality_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_quality_counts(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_quality_counts_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_write_protocol(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_write_protocol_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_write_protocol_count(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_write_protocol_count_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn validate_regex_contract(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::validate_regex_contract_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_rule_import(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::prepare_rule_import_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn commit_rule_import(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::commit_rule_import_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn build_scope_index(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::build_scope_index_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_rule_candidates(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_rule_candidates_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn evaluate_scope_gate(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::evaluate_scope_gate_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn native_schema_fingerprint() -> String {
    native_core::native_schema_fingerprint_impl()
}

#[pyfunction]
fn inspect_scope_index_storage(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::inspect_scope_index_storage_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn write_scope_index_storage(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::write_scope_index_storage_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn rebuild_scope_index_storage(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::rebuild_scope_index_storage_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn collect_note_tag_sources(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::collect_note_tag_sources_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn scan_font_replacements(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::scan_font_replacements_impl(&payload_json).map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn parse_javascript_string_spans(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::parse_javascript_string_spans_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn parse_javascript_string_spans_batch(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::parse_javascript_string_spans_batch_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn collect_runtime_literal_issue_facts(py: Python<'_>, payload_json: String) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::collect_runtime_literal_issue_facts_impl(&payload_json)
            .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pyfunction]
fn build_write_back_plan(
    py: Python<'_>,
    game_path: String,
    db_path: String,
    setting_payload_json: String,
    mode: String,
    confirm_font_overwrite: bool,
) -> PyResult<String> {
    let result = py.detach(move || {
        native_core::build_write_back_plan_impl(
            &game_path,
            &db_path,
            &setting_payload_json,
            &mode,
            confirm_font_overwrite,
        )
        .map_err(|error| error.to_string())
    });
    result.map_err(PyValueError::new_err)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(native_contract_version, m)?)?;
    m.add_function(wrap_pyfunction!(native_thread_count, m)?)?;
    m.add_function(wrap_pyfunction!(configure_runtime_threads, m)?)?;
    m.add_function(wrap_pyfunction!(scan_quality, m)?)?;
    m.add_function(wrap_pyfunction!(scan_quality_counts, m)?)?;
    m.add_function(wrap_pyfunction!(scan_write_protocol, m)?)?;
    m.add_function(wrap_pyfunction!(scan_write_protocol_count, m)?)?;
    m.add_function(wrap_pyfunction!(validate_regex_contract, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_rule_import, m)?)?;
    m.add_function(wrap_pyfunction!(commit_rule_import, m)?)?;
    m.add_function(wrap_pyfunction!(build_scope_index, m)?)?;
    m.add_function(wrap_pyfunction!(scan_rule_candidates, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_scope_gate, m)?)?;
    m.add_function(wrap_pyfunction!(native_schema_fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(inspect_scope_index_storage, m)?)?;
    m.add_function(wrap_pyfunction!(write_scope_index_storage, m)?)?;
    m.add_function(wrap_pyfunction!(rebuild_scope_index_storage, m)?)?;
    m.add_function(wrap_pyfunction!(collect_note_tag_sources, m)?)?;
    m.add_function(wrap_pyfunction!(scan_font_replacements, m)?)?;
    m.add_function(wrap_pyfunction!(parse_javascript_string_spans, m)?)?;
    m.add_function(wrap_pyfunction!(parse_javascript_string_spans_batch, m)?)?;
    m.add_function(wrap_pyfunction!(collect_runtime_literal_issue_facts, m)?)?;
    m.add_function(wrap_pyfunction!(build_write_back_plan, m)?)?;
    Ok(())
}
