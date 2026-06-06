"""生成 A.T.T MZ 开发版/发行版 Skill 与 Codex 子代理配置。"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_DIR = ROOT / "skills" / "att-mz-protocol"
TEMPLATE_DIR = PROTOCOL_DIR / "templates"
REFERENCE_TEMPLATE_DIR = TEMPLATE_DIR / "references"
DEV_SKILL_DIR = ROOT / "skills" / "att-mz"
RELEASE_SKILL_DIR = ROOT / "skills" / "att-mz-release"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cli import build_parser  # noqa: E402
from app.cli.parser import parser_command_names  # noqa: E402


@dataclass(frozen=True)
class Profile:
    """开发版或发行版 Skill 生成配置。"""

    profile_id: str
    skill_name: str
    title: str
    description: str
    root_label: str
    root_placeholder: str
    command_prefix: str
    command_example: str
    root_description: str
    workspace_forbidden_target: str
    docs_boundary: str
    troubleshooting_boundary: str
    forbidden_environment: str
    output_dir: Path


@dataclass(frozen=True)
class Stage:
    """流程阶段声明。"""

    stage_id: str
    title: str
    target: str
    inputs: list[str]
    outputs: list[str]
    pass_criteria: list[str]
    stop_conditions: list[str]
    commands: list[str]
    references: list[str]
    read_when: str


@dataclass(frozen=True)
class Subagent:
    """子代理角色声明。"""

    agent_id: str
    description: str
    mission: str
    inputs: list[str]
    unique_output: str
    report_schema: list[str]
    forbidden_actions: list[str]
    cross_review_by: list[str]
    developer_instructions: str


def read_text(path: Path) -> str:
    """读取 UTF-8 文本。"""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """写入 UTF-8 文本，统一结尾换行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text = text + "\n"
    path.write_text(text, encoding="utf-8")


def read_toml(path: Path) -> dict[str, object]:
    """读取 TOML 为可收窄对象字典。"""
    return cast(dict[str, object], tomllib.loads(read_text(path)))


def require_str(data: dict[str, object], key: str) -> str:
    """读取必需字符串字段。"""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} 必须是非空字符串")
    return value


def require_str_list(data: dict[str, object], key: str) -> list[str]:
    """读取必需字符串列表字段。"""
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{key} 必须是非空字符串数组")
    return cast(list[str], value)


def require_dict_list(data: dict[str, object], key: str) -> list[dict[str, object]]:
    """读取必需对象数组字段。"""
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} 必须是对象数组")
    return cast(list[dict[str, object]], value)


def load_profile(path: Path, output_dir: Path) -> Profile:
    """从 profile TOML 读取运行面差异。"""
    data = read_toml(path)
    return Profile(
        profile_id=require_str(data, "profile_id"),
        skill_name=require_str(data, "skill_name"),
        title=require_str(data, "title"),
        description=require_str(data, "description"),
        root_label=require_str(data, "root_label"),
        root_placeholder=require_str(data, "root_placeholder"),
        command_prefix=require_str(data, "command_prefix"),
        command_example=require_str(data, "command_example"),
        root_description=require_str(data, "root_description"),
        workspace_forbidden_target=require_str(data, "workspace_forbidden_target"),
        docs_boundary=require_str(data, "docs_boundary"),
        troubleshooting_boundary=require_str(data, "troubleshooting_boundary"),
        forbidden_environment=require_str(data, "forbidden_environment"),
        output_dir=output_dir,
    )


def load_stages() -> list[Stage]:
    """读取流程阶段 manifest。"""
    workflow = read_toml(PROTOCOL_DIR / "workflow.toml")
    stages: list[Stage] = []
    for stage in require_dict_list(workflow, "stages"):
        stages.append(
            Stage(
                stage_id=require_str(stage, "id"),
                title=require_str(stage, "title"),
                target=require_str(stage, "target"),
                inputs=require_str_list(stage, "inputs"),
                outputs=require_str_list(stage, "outputs"),
                pass_criteria=require_str_list(stage, "pass_criteria"),
                stop_conditions=require_str_list(stage, "stop_conditions"),
                commands=require_str_list(stage, "commands"),
                references=require_str_list(stage, "references"),
                read_when=require_str(stage, "read_when"),
            )
        )
    return stages


def load_subagents() -> list[Subagent]:
    """读取子代理角色 manifest。"""
    subagents = read_toml(PROTOCOL_DIR / "subagents.toml")
    agents: list[Subagent] = []
    for agent in require_dict_list(subagents, "agents"):
        agents.append(
            Subagent(
                agent_id=require_str(agent, "id"),
                description=require_str(agent, "description"),
                mission=require_str(agent, "mission"),
                inputs=require_str_list(agent, "inputs"),
                unique_output=require_str(agent, "unique_output"),
                report_schema=require_str_list(agent, "report_schema"),
                forbidden_actions=require_str_list(agent, "forbidden_actions"),
                cross_review_by=require_str_list(agent, "cross_review_by"),
                developer_instructions=require_str(agent, "developer_instructions"),
            )
        )
    return agents


def validate_unique(values: list[str], label: str) -> None:
    """校验 id 唯一。"""
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{label} 存在重复 id: {', '.join(duplicates)}")


def validate_protocol(stages: list[Stage], subagents: list[Subagent]) -> None:
    """校验 canonical 协议源可生成当前公开契约。"""
    validate_unique([stage.stage_id for stage in stages], "workflow.toml")
    validate_unique([agent.agent_id for agent in subagents], "subagents.toml")
    command_names = parser_command_names(build_parser())
    for stage in stages:
        for command in stage.commands:
            if command not in command_names:
                raise ValueError(f"阶段 {stage.stage_id} 引用了未知 CLI 命令: {command}")
        for reference in stage.references:
            if not (REFERENCE_TEMPLATE_DIR / f"{reference}.in").is_file():
                raise ValueError(f"阶段 {stage.stage_id} 引用了不存在的 reference 模板: {reference}")
    agent_ids = {agent.agent_id for agent in subagents}
    for agent in subagents:
        for reviewer in agent.cross_review_by:
            if reviewer not in agent_ids:
                raise ValueError(f"子代理 {agent.agent_id} 引用了不存在的交叉审查代理: {reviewer}")


def bullet_list(items: list[str]) -> str:
    """渲染 Markdown bullet 列表。"""
    return "\n".join(f"- {item}" for item in items)


def inline_code_list(items: list[str]) -> str:
    """渲染行内代码列表。"""
    return "、".join(f"`{item}`" for item in items)


def render_stage_index(stages: list[Stage]) -> str:
    """渲染主 Skill 的阶段索引表。"""
    rows = ["| 阶段 | 目标 | 命令 | 必读参考 |", "| --- | --- | --- | --- |"]
    for stage in stages:
        rows.append(
            f"| {stage.title} | {stage.target} | {inline_code_list(stage.commands)} | {inline_code_list(stage.references)} |"
        )
    return "\n".join(rows)


def render_reference_matrix(stages: list[Stage]) -> str:
    """渲染按需参考资料表。"""
    rows = ["| 主要工作 | 必读参考资料 | 读取时机 |", "| --- | --- | --- |"]
    for stage in stages:
        rows.append(f"| {stage.title} | {inline_code_list(stage.references)} | {stage.read_when} |")
    return "\n".join(rows)


def render_stage_details(stages: list[Stage]) -> str:
    """渲染阶段详情 reference。"""
    sections: list[str] = []
    for index, stage in enumerate(stages, start=1):
        sections.append(
            "\n".join(
                [
                    f"## {index}. {stage.title}",
                    "",
                    f"目标：{stage.target}",
                    "",
                    "输入：",
                    bullet_list(stage.inputs),
                    "",
                    "输出：",
                    bullet_list(stage.outputs),
                    "",
                    "常用命令：",
                    bullet_list([f"`{command}`" for command in stage.commands]),
                    "",
                    "通过标准：",
                    bullet_list(stage.pass_criteria),
                    "",
                    "停止条件：",
                    bullet_list(stage.stop_conditions),
                    "",
                    f"按需读取：{inline_code_list(stage.references)}。",
                ]
            )
        )
    return "\n\n".join(sections)


def render_hard_stops(stages: list[Stage]) -> str:
    """汇总主 Skill 硬停止规则。"""
    stops: list[str] = []
    for stage in stages:
        for condition in stage.stop_conditions:
            stops.append(f"{stage.title}：{condition}")
    return bullet_list(stops)


def render_write_gates(stages: list[Stage]) -> str:
    """渲染写回前门槛摘要。"""
    for stage in stages:
        if stage.stage_id == "write_back":
            return bullet_list(stage.pass_criteria)
    raise ValueError("workflow.toml 缺少 write_back 阶段")


def render_subagent_rows(subagents: list[Subagent]) -> str:
    """渲染子代理角色表。"""
    rows = ["| 子代理 | 使命 | 唯一输出 | 交叉审查 |", "| --- | --- | --- | --- |"]
    for agent in subagents:
        reviewers = inline_code_list(agent.cross_review_by) if agent.cross_review_by else "主代理"
        rows.append(f"| `{agent.agent_id}` | {agent.mission} | `{agent.unique_output}` | {reviewers} |")
    return "\n".join(rows)


def render_subagent_details(subagents: list[Subagent]) -> str:
    """渲染子代理协作详情 reference。"""
    sections: list[str] = []
    for agent in subagents:
        sections.append(
            "\n".join(
                [
                    f"## `{agent.agent_id}`",
                    "",
                    f"使命：{agent.mission}",
                    "",
                    "输入：",
                    bullet_list(agent.inputs),
                    "",
                    f"唯一输出：`{agent.unique_output}`",
                    "",
                    "报告字段：",
                    bullet_list([f"`{field}`" for field in agent.report_schema]),
                    "",
                    "禁止动作：",
                    bullet_list(agent.forbidden_actions),
                    "",
                    f"交叉审查：{inline_code_list(agent.cross_review_by) if agent.cross_review_by else '由主代理审查'}。",
                ]
            )
        )
    return "\n\n".join(sections)


def profile_values(profile: Profile, stages: list[Stage], subagents: list[Subagent]) -> dict[str, str]:
    """汇总模板变量。"""
    return {
        "profile_id": profile.profile_id,
        "skill_name": profile.skill_name,
        "title": profile.title,
        "description": profile.description,
        "root_label": profile.root_label,
        "root_placeholder": profile.root_placeholder,
        "command_prefix": profile.command_prefix,
        "command_example": profile.command_example,
        "root_description": profile.root_description,
        "workspace_forbidden_target": profile.workspace_forbidden_target,
        "docs_boundary": profile.docs_boundary,
        "troubleshooting_boundary": profile.troubleshooting_boundary,
        "forbidden_environment": profile.forbidden_environment,
        "stage_index": render_stage_index(stages),
        "reference_matrix": render_reference_matrix(stages),
        "stage_details": render_stage_details(stages),
        "hard_stops": render_hard_stops(stages),
        "write_gates": render_write_gates(stages),
        "subagent_rows": render_subagent_rows(subagents),
        "subagent_details": render_subagent_details(subagents),
    }


def render_template(template: str, values: dict[str, str], template_path: Path) -> str:
    """替换模板变量并拒绝未知占位符。"""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    unknown = sorted(set(re.findall(r"{{\s*[^}]+\s*}}", rendered)))
    if unknown:
        raise ValueError(f"{template_path} 包含未知占位符: {', '.join(unknown)}")
    return rendered.rstrip() + "\n"


def render_profile_text(template_path: Path, profile: Profile, stages: list[Stage], subagents: list[Subagent]) -> str:
    """按运行面渲染一个模板。"""
    values = profile_values(profile, stages, subagents)
    rendered = render_template(read_text(template_path), values, template_path)
    if profile.profile_id == "release":
        rendered = rendered.replace("uv run python main.py", profile.command_prefix)
        rendered = rendered.replace("<项目目录>", profile.root_placeholder)
        rendered = rendered.replace("项目目录", profile.root_label)
        rendered = rendered.replace("开发版", "发行版")
    return rendered


def generated_files(profiles: list[Profile], stages: list[Stage], subagents: list[Subagent]) -> dict[Path, str]:
    """生成全部目标文件内容。"""
    files: dict[Path, str] = {}
    skill_template = TEMPLATE_DIR / "SKILL.md.in"
    for profile in profiles:
        files[profile.output_dir / "SKILL.md"] = render_profile_text(skill_template, profile, stages, subagents)
        for template_path in sorted(REFERENCE_TEMPLATE_DIR.glob("*.md.in")):
            output_name = template_path.name.removesuffix(".in")
            files[profile.output_dir / "references" / output_name] = render_profile_text(
                template_path,
                profile,
                stages,
                subagents,
            )
    return files


def ensure_outputs_are_allowed(files: dict[Path, str]) -> None:
    """确认生成器不会写出预期目录外的文件。"""
    allowed_roots = (DEV_SKILL_DIR, RELEASE_SKILL_DIR)
    for path in files:
        resolved = path.resolve()
        if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
            raise ValueError(f"生成目标越界: {path}")


def check_files(files: dict[Path, str]) -> list[str]:
    """比较生成内容和工作区内容。"""
    failures: list[str] = []
    for path, expected in sorted(files.items()):
        if not path.exists():
            failures.append(f"缺少生成文件: {path.relative_to(ROOT)}")
            continue
        actual = read_text(path)
        if actual != expected:
            diff = "\n".join(
                difflib.unified_diff(
                    actual.splitlines(),
                    expected.splitlines(),
                    fromfile=f"current/{path.relative_to(ROOT)}",
                    tofile=f"generated/{path.relative_to(ROOT)}",
                    lineterm="",
                    n=3,
                )
            )
            failures.append(diff)
    return failures


def write_files(files: dict[Path, str]) -> None:
    """写出全部生成文件。"""
    for path, text in sorted(files.items()):
        write_text(path, text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成并校验 A.T.T MZ Skill 协议文件")
    group = parser.add_mutually_exclusive_group(required=True)
    _ = group.add_argument("--write", action="store_true", help="写出生成文件")
    _ = group.add_argument("--check", action="store_true", help="只校验生成文件是否最新")
    return parser.parse_args(argv)


def build_generated_files() -> dict[Path, str]:
    """读取 canonical 源并生成目标文件。"""
    stages = load_stages()
    subagents = load_subagents()
    validate_protocol(stages, subagents)
    profiles = [
        load_profile(PROTOCOL_DIR / "profiles" / "dev.toml", DEV_SKILL_DIR),
        load_profile(PROTOCOL_DIR / "profiles" / "release.toml", RELEASE_SKILL_DIR),
    ]
    files = generated_files(profiles, stages, subagents)
    ensure_outputs_are_allowed(files)
    return files


def main(argv: list[str] | None = None) -> int:
    """执行生成或校验。"""
    namespace = parse_args(sys.argv[1:] if argv is None else argv)
    files = build_generated_files()
    if namespace.write:
        write_files(files)
        return 0
    failures = check_files(files)
    if failures:
        print("Skill 协议生成文件不是最新，请运行: uv run python scripts/generate_skill_protocol.py --write")
        print("\n\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
