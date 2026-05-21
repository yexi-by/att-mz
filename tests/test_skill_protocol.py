"""Skill 执行协议回归测试。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEV_SKILL = ROOT / "skills" / "att-mz" / "SKILL.md"
RELEASE_SKILL = ROOT / "skills" / "att-mz-release" / "SKILL.md"
DEV_REFERENCES = ROOT / "skills" / "att-mz" / "references"
RELEASE_REFERENCES = ROOT / "skills" / "att-mz-release" / "references"

REQUIRED_REFERENCE_NAMES = {
    "cli-command-contract.md",
    "workspace-schema.md",
    "rpg-maker-mv-mz-world-knowledge.md",
    "mv-virtual-namebox-rules.md",
    "terminology-workflow.md",
    "external-rules-workflow.md",
    "plugin-rules-agent-task.md",
    "event-command-rules-agent-task.md",
    "note-tag-rules-agent-task.md",
    "placeholder-rules.md",
    "structured-placeholder-rules.md",
    "subtask-package-mode.md",
    "failure-recovery.md",
    "feedback-iteration.md",
    "translation-rule-examples.md",
}


def read(path: Path) -> str:
    """读取 UTF-8 文本。"""
    return path.read_text(encoding="utf-8")


def test_main_skills_are_progressive_workflow_entrypoints() -> None:
    """主 Skill 只承载流程入口、矩阵、强制读取和硬门槛。"""
    for path in (DEV_SKILL, RELEASE_SKILL):
        text = read(path)
        assert len(text.splitlines()) <= 180
        for phrase in [
            "主文件只描述阶段、边界、必读参考资料和停止条件",
            "## 按需参考资料",
            "## 主要工作矩阵",
            "## 新游戏主流程",
            "## 二次翻译主流程",
            "## 子代理与外部协作",
            "## 写进游戏文件前硬门槛",
            "## 工具排障边界",
            "## 禁止做法",
            "对用户报告时，把内部状态、字段名和命令结果转成业务影响与下一步动作",
            "派发子代理时不能只概括任务",
            "必须复制对应任务契约",
        ]:
            assert phrase in text
        for reference_name in REQUIRED_REFERENCE_NAMES:
            assert f"`references/{reference_name}`" in text


def test_main_skill_matrix_uses_cohesive_work_units() -> None:
    """主要工作矩阵按工作能力划分，而不是按命令百科展开。"""
    text = read(DEV_SKILL)
    expected_rows = [
        "| 启动与注册 |",
        "| MV 虚拟名字框 |",
        "| 术语工程 |",
        "| 外部文本规则 |",
        "| 占位符收束 |",
        "| 正文翻译 |",
        "| 手动修复 |",
        "| 写进游戏文件 |",
        "| 试玩反馈 |",
        "| 工具排障 |",
    ]
    for row in expected_rows:
        assert row in text

    assert "### 命令 I/O 合约" not in text
    assert "### 工作区 JSON 格式契约" not in text
    assert "术语候选子代理任务单" not in text


def test_write_back_gate_does_not_require_empty_source_residual_rules() -> None:
    """源文保留例外只在需要放行源语言片段时才是写回前置。"""
    for path in (DEV_SKILL, RELEASE_SKILL):
        text = read(path)
        assert "源文保留例外已经导入" not in text
        assert "质量检查没有提示源文残留时，不把空源文保留例外当写回前置" in text
        assert "三类外部规则、普通占位符规则和结构化占位符规则已经导入" in text


def test_main_skill_does_not_embed_status_wording_map() -> None:
    """用户表达约束保持通用，不在 Skill 主入口列内部状态词映射。"""
    combined_text = read(DEV_SKILL) + "\n" + read(RELEASE_SKILL)
    forbidden_phrases = [
        "不要直接对用户说",
        "`pending`",
        "`quality_error`",
        "`overwide_line`",
        "`location_path`",
        "`translation_lines`",
        "入库",
        "缓存",
        "门禁",
        "导出骨架",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined_text


def test_development_and_release_skill_structure_match() -> None:
    """开发版和发行版 Skill 保持同构章节。"""
    dev_text = read(DEV_SKILL)
    release_text = read(RELEASE_SKILL)
    dev_headings = [line for line in dev_text.splitlines() if line.startswith("#")]
    release_headings = [line for line in release_text.splitlines() if line.startswith("#")]

    assert release_headings[0] == "# A.T.T MZ 发行版 Skill"
    assert release_headings[1:] == dev_headings[1:]
    assert "name: att-mz" in dev_text.split("---", 2)[1]
    assert "name: att-mz-release" in release_text.split("---", 2)[1]


def test_release_skill_uses_packaged_cli_boundary() -> None:
    """发行版 Skill 使用 exe 入口，并把源码排障导回源码仓库。"""
    text = read(RELEASE_SKILL)
    for phrase in [
        ".\\att-mz.exe --agent-mode <命令> ...",
        "不要运行 `uv run python main.py`",
        "不要安装 Python、Rust、uv 或 maturin",
        "不要读取项目源码",
        "必须切换到源码仓库和开发版 Skill",
    ]:
        assert phrase in text

    for reference_path in RELEASE_REFERENCES.glob("*.md"):
        reference_text = read(reference_path)
        assert "uv run python main.py --agent-mode" not in reference_text


def test_required_references_exist_in_both_skill_variants() -> None:
    """开发版和发行版都携带完整按需参考资料。"""
    dev_names = {path.name for path in DEV_REFERENCES.glob("*.md")}
    release_names = {path.name for path in RELEASE_REFERENCES.glob("*.md")}

    assert REQUIRED_REFERENCE_NAMES <= dev_names
    assert REQUIRED_REFERENCE_NAMES <= release_names

    identical_reference_names = {
        "translation-rule-examples.md",
        "structured-placeholder-rules.md",
        "mv-virtual-namebox-rules.md",
        "rpg-maker-mv-mz-world-knowledge.md",
        "workspace-schema.md",
    }
    for reference_name in identical_reference_names:
        assert read(RELEASE_REFERENCES / reference_name) == read(DEV_REFERENCES / reference_name)


def test_cli_command_contract_reference_defines_stage_commands() -> None:
    """命令契约 reference 承载命令、成功判断和失败处理。"""
    text = read(DEV_REFERENCES / "cli-command-contract.md")
    for phrase in [
        "默认前缀",
        "uv run python main.py --agent-mode <命令> ...",
        "文件型规则一律用 `--input <文件>`",
        "不要用 `--rules \"$(cat ...)\"`",
        "不要把大 JSON 塞进命令行",
        "注册游戏必须显式传 `--source-language ja` 或 `--source-language en`",
        "`doctor --no-check-llm --json`",
        "`prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --json`",
        "`validate-plugin-rules --game <游戏标题> --input <规则文件> --json`",
        "`validate-note-tag-rules --game <游戏标题> --input <规则文件> --json`",
        "`scan-placeholder-candidates --game <游戏标题> --input <规则文件> --json`",
        "`translation-status --game <游戏标题> --json`",
        "`audit-coverage --game <游戏标题> --json`",
        "`quality-report --game <游戏标题> --json`",
        "`verify-feedback-text --game <游戏标题> --input <反馈原文清单> --json`",
        "`write-back --game <游戏标题> --json`",
        "日文和英文游戏都使用通用源文残留命令",
    ]:
        assert phrase in text


def test_cli_contract_keeps_recovery_and_terminal_antiregression_details() -> None:
    """命令契约保留恢复字段、插件漂移和 Windows 编码排障能力。"""
    for references in (DEV_REFERENCES, RELEASE_REFERENCES):
        cli_text = read(references / "cli-command-contract.md")
        for phrase in [
            "summary.deleted_translation_backup_path",
            "details.deleted_translation_backup.path",
            "当前插件配置哈希",
            "插件哈希或当前配置不一致",
            "重新准备工作区，不猜路径",
            "$OutputEncoding = [System.Text.UTF8Encoding]::new()",
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()",
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()",
            "Path.read_text/write_text(..., encoding=\"utf-8\")",
            "PowerShell 写文件必须显式 `-Encoding utf8`",
            "不要基于乱码内容修改 JSON、规则或译文",
            "Unicode code point",
            "stderr 进度行不能当作命令结果 JSON",
        ]:
            assert phrase in cli_text

        failure_text = read(references / "failure-recovery.md")
        assert "插件哈希或当前配置不一致" in failure_text
        assert "重新运行 `prepare-agent-workspace`" in failure_text
        assert "不要靠猜改路径" in failure_text


def test_workspace_schema_reference_defines_json_contracts() -> None:
    """工作区 schema reference 承载外部 JSON 契约。"""
    text = read(DEV_REFERENCES / "workspace-schema.md")
    for phrase in [
        "mv-virtual-namebox-rules.json",
        "placeholder-rules.json",
        "structured-placeholder-rules.json",
        "terminology/field-terms.json",
        "terminology/glossary.json",
        "plugin-rules.json",
        "event-command-rules.json",
        "note-tag-rules.json",
        "pending-translations.json",
        "quality-fix-template.json",
        "reset-translations.json",
        "source-residual-rules.json",
        "MV 的 `speaker_names` 是虚拟名字框说话人术语",
        "allowed_terms",
        "check_group",
        "禁止在 `pending-translations.json` 内新增例外字段",
    ]:
        assert phrase in text


def test_terminology_reference_defines_first_round_contract() -> None:
    """术语 reference 承载第一轮子代理和主代理合并职责。"""
    text = read(DEV_REFERENCES / "terminology-workflow.md")
    for phrase in [
        "第一轮只处理术语候选",
        "terminology/subtasks/sources/speaker_and_actor_terms.json",
        "terminology/subtasks/candidates/equipment_terms.json",
        "术语候选子代理任务必须包含",
        "主代理合并职责",
        "字段译名表的 value 是最终写进游戏字段的完整文本",
        "正文术语表只保留 `terms` 顶层对象",
        "import-terminology",
    ]:
        assert phrase in text


def test_external_rule_references_define_second_round_contracts() -> None:
    """外部规则 references 承载第二轮规则判断和三类任务契约。"""
    workflow_text = read(DEV_REFERENCES / "external-rules-workflow.md")
    for phrase in [
        "插件规则、事件指令规则和 Note 标签规则可以并行处理",
        "三类外部规则全部导入后，才能重新生成和收束占位符规则",
        "plugin-rules-agent-task.md",
        "event-command-rules-agent-task.md",
        "note-tag-rules-agent-task.md",
        "插件文本触发键",
        "中文显示值 -> 原始触发值",
        "派发子代理时不能只概括",
        "必须复制对应任务契约",
        "输入文件、唯一可写文件和校验命令",
    ]:
        assert phrase in workflow_text

    note_task_text = read(DEV_REFERENCES / "note-tag-rules-agent-task.md")
    for phrase in [
        "不读取项目源码、数据库或程序内部对象",
        "`<工作区>/note-tag-candidates.json`",
        "唯一可写文件：`<工作区>/note-tag-rules.json`",
        "格式为 `{data文件名或文件模式: [note标签名, ...]}`",
        "合法空结果是 `{}`",
        "validate-note-tag-rules",
        "不要直接改游戏 `data/*.json` 的 `note` 字段",
    ]:
        assert phrase in note_task_text


def test_placeholder_reference_defines_scope_and_mixed_protocol_strategy() -> None:
    """普通占位符 reference 承载作用域和混合协议处理策略。"""
    text = read(DEV_REFERENCES / "placeholder-rules.md")
    for phrase in [
        "只作用于当前已经进入正文翻译集合的文本",
        "已导入插件参数规则命中的文本",
        "已导入事件指令规则命中的文本",
        "已导入 Note 标签规则命中的文本",
        "不能让未被插件规则、事件指令规则或 Note 标签规则选中的字符串进入翻译",
        "三类外部规则改变后，必须重新运行",
        "不要因为它混有协议语法就一概排除",
        "去掉 `[CUSTOM_...]` 后仍应保留需要翻译的玩家可见文本",
        "`summary.uncovered_count` 必须等于 0",
        "小写 `\\n` 是游戏文本中的字面量换行",
        r"原文是 `\F3[66」「` 时，译文也保留 `\F3[66」「`",
    ]:
        assert phrase in text


def test_structured_placeholder_reference_defines_contract() -> None:
    """结构化占位符 reference 定义可执行外部契约。"""
    text = read(DEV_REFERENCES / "structured-placeholder-rules.md")
    for phrase in [
        "# 结构化占位符规则",
        "普通正则占位符规则并列",
        "translatable_group",
        "protected_groups",
        "paired_shell_rules",
        "合法空结构",
        "validate-structured-placeholder-rules",
        "scan-structured-placeholder-candidates",
        "import-structured-placeholder-rules",
        "源文残留检查会先在占位符仍存在的形态下执行，再恢复外壳",
    ]:
        assert phrase in text


def test_failure_and_feedback_references_define_recovery_loops() -> None:
    """失败恢复和试玩反馈 references 承载修复闭环。"""
    failure_text = read(DEV_REFERENCES / "failure-recovery.md")
    for phrase in [
        "`translate` 返回 0 只表示本轮命令正常结束",
        "连续多轮同类失败不下降",
        "export-quality-fix-template",
        "export-pending-translations",
        "validate-source-residual-rules",
        "reset-translations",
        "禁止用它掩盖整句漏翻",
        "`allowed_terms` 必须是非空字符串数组",
        "存在于正则里的 `check_group`",
    ]:
        assert phrase in failure_text

    feedback_text = read(DEV_REFERENCES / "feedback-iteration.md")
    for phrase in [
        "试玩反馈是正式翻译流程的一部分",
        "问题截图或原文片段",
        "verify-feedback-text",
        "scan-plugin-source-text",
        "反馈清单 -> 定位 -> 补规则或补译文 -> audit-coverage -> quality-report",
        "只有用户明确选择完整重译时",
        "用户确认本轮试玩反馈已经处理完成",
        "cleanup-agent-workspace --workspace <工作区> --json",
    ]:
        assert phrase in feedback_text


def test_translation_rule_examples_are_progressive_references_not_skill_rules() -> None:
    """具体样例只放在 references，并声明不能当作当前游戏固定答案。"""
    dev_reference = DEV_REFERENCES / "translation-rule-examples.md"
    release_reference = RELEASE_REFERENCES / "translation-rule-examples.md"
    assert read(release_reference) == read(dev_reference)

    text = read(dev_reference)
    for phrase in [
        "# 翻译规则样例参考",
        "本文件用于在对应步骤中渐进式读取",
        "所有样例都使用抽象占位符",
        "不代表任何游戏、插件、指令编码、文件名、路径层级或标签名的固定规则",
        "## 术语候选样例",
        "## 占位符规则样例",
        "## 三类外部规则样例",
        "### 插件规则",
        "### 事件指令规则",
        "### Note 标签规则",
    ]:
        assert phrase in text


def test_docs_do_not_own_agent_task_contracts() -> None:
    """Agent 任务契约归属 Skill references。"""
    docs_dir = ROOT / "docs"
    forbidden_fragments = [
        "plugin-rules-agent-prompt",
        "event-command-rules-agent-prompt",
        "note-tag-rules-agent-prompt",
    ]
    for path in docs_dir.rglob("*.md"):
        for fragment in forbidden_fragments:
            assert fragment not in path.name

    combined_skill_text = read(DEV_SKILL) + "\n" + read(RELEASE_SKILL)
    assert "`docs/plugin-rules-agent-prompt.md`" not in combined_skill_text
    assert "`docs/event-command-rules-agent-prompt.md`" not in combined_skill_text


def test_subtask_package_mode_document_defines_portable_contract() -> None:
    """外部协作任务包文档说明可带走任务和主代理验收边界。"""
    text = read(DEV_REFERENCES / "subtask-package-mode.md")
    for phrase in [
        "# 外部协作任务包模式",
        "它不是新的 CLI 功能",
        "用途",
        "输入",
        "处理逻辑",
        "输出格式",
        "禁止事项",
        "空结果",
        "主代理验收步骤",
        "一个任务包文件夹只对应一个任务",
        "prompt.md",
        "manifest.json",
        "answer-template.json",
        "answer.json",
        "context/",
        "任务包文件夹必须能被压缩后远程分发",
        "任务包只能覆盖五个术语候选分组、插件规则、事件指令规则和 Note 标签规则",
    ]:
        assert phrase in text

    for phrase in ["C:\\", "D:\\", "Users\\", "测试样本", "Sexual_conflict", "生意気"]:
        assert phrase not in text


def test_release_packaging_script_copies_all_skill_references() -> None:
    """发布脚本复制发行版 Skill 和全部 references。"""
    text = read(ROOT / "scripts" / "build_release.py")
    for phrase in [
        "RELEASE_SKILL_SOURCE",
        "RELEASE_SKILL_REFERENCES_SOURCE",
        '"att-mz-release" / "SKILL.md"',
        '"att-mz-release" / "references"',
        "reference_path in sorted(RELEASE_SKILL_REFERENCES_SOURCE.glob(\"*.md\"))",
        "reference_path.name",
        "copy_packaged_release_skill",
        '"name: att-mz-release", "name: att-mz"',
        '"skills" / "att-mz" / "SKILL.md"',
        "ensure_github_actions_environment",
        "发行版构建只能在 GitHub Actions release 工作流中执行",
        "configure_stdio_encoding",
        'encoding="utf-8"',
        'errors="replace"',
    ]:
        assert phrase in text


def test_text_translation_prompt_keeps_protocol_minimal() -> None:
    """正文翻译提示词只说明可见任务，不解释项目内部保护机制。"""
    text = read(ROOT / "prompts" / "text_translation_ja_to_zh_system.md")

    for phrase in [
        "`[[术语表]]`",
        "`short_text`：按一个完整字段翻译，`translation_lines` 必须只包含 1 个字符串",
        "形如 `[RMMZ_...]` 或 `[CUSTOM_...]` 的片段是必须原样保留的文本标记。",
    ]:
        assert phrase in text

    for phrase in [
        "# 术语表",
        "如果原文内部已有换行",
        "常用于变量",
        "保护",
        "恢复",
        "写回",
        "占位符",
    ]:
        assert phrase not in text
