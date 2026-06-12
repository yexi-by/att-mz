"""Agent 工作区 manifest 当前输入模型测试。"""

import json
from pathlib import Path

import pytest

from app.agent_toolkit.service import AgentToolkitService


@pytest.mark.asyncio
async def test_cleanup_agent_workspace_reports_manifest_unlisted_files(tmp_path: Path) -> None:
    """cleanup 只清理 manifest.files，manifest 外文件必须保留并说明不参与本轮。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    current_file = workspace / "plugin-rules.json"
    stale_file = workspace / "plugin-source-rules.json"
    _ = current_file.write_text("[]\n", encoding="utf-8")
    _ = stale_file.write_text("[]\n", encoding="utf-8")
    _ = (workspace / "manifest.json").write_text(
        json.dumps({"files": [str(current_file)]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    service = AgentToolkitService()

    report = await service.cleanup_agent_workspace(workspace=workspace)

    assert report.status == "warning"
    assert not current_file.exists()
    assert stale_file.exists()
    assert {warning.code for warning in report.warnings} == {"workspace_unlisted_files_ignored"}
    assert "manifest 外文件" in report.warnings[0].message
    assert "不会参与本轮验收" in report.warnings[0].message
