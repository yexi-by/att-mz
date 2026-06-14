"""
配置模型定义模块。

本模块定义 CLI 翻译流程的运行配置：正文模型服务、正文切批、
正文翻译和文本过滤规则。RPG Maker 标准控制符由代码协议负责保护，自定义正则
占位符规则由当前游戏数据库或 CLI 显式输入提供。
"""

import re
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from app.language import (
    DEFAULT_SOURCE_LANGUAGE,
    SUPPORTED_SOURCE_LANGUAGES,
    SourceLanguage,
    SourceResidualDetectionProfile,
    SourceTextExclusionProfile,
)
from app.llm_request_body_extra import LLMRequestBodyExtra, normalize_request_body_extra
from app.rmmz.engine import EngineKind


class StrictBaseModel(BaseModel):
    """项目统一使用的严格配置模型基类。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


type LLMProviderType = Literal["openai"]

LLM_CLIENT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class LLMClientSetting(StrictBaseModel):
    """一个可被命令行选择的模型客户端配置。"""

    name: str = Field(title="客户端名称", description="命令行选择模型客户端时使用的唯一名称。")
    provider_type: LLMProviderType = Field(title="提供商类型", description="当前只支持 openai。")
    base_url: str = Field(title="服务 URL", description="模型服务地址。")
    api_key: str = Field(title="API 密钥", description="访问模型服务所需凭据。")
    model: str = Field(title="模型名称", description="实际调用的模型标识。")
    timeout: int = Field(gt=0, title="超时时间", description="单位为秒。")
    request_body_extra: LLMRequestBodyExtra = Field(
        default_factory=dict,
        title="模型请求体额外参数",
        description="透传到 OpenAI 兼容 Chat Completions 请求体的 JSON 对象。",
    )

    @field_validator("request_body_extra", mode="before")
    @classmethod
    def _validate_request_body_extra(cls, value: object) -> LLMRequestBodyExtra:
        """解析并校验模型请求体额外参数。"""
        return normalize_request_body_extra(value, context="llm.clients.request_body_extra")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """客户端名称必须适合作为稳定命令行标识。"""
        if not LLM_CLIENT_NAME_PATTERN.fullmatch(value):
            raise ValueError("llm.clients.name 只能使用小写字母、数字、短横线和下划线")
        return value

    @field_validator("provider_type", mode="before")
    @classmethod
    def _validate_provider_type(cls, value: object) -> object:
        """当前只开放 OpenAI 兼容协议类型。"""
        if value != "openai":
            raise ValueError("llm.clients.provider_type 当前只支持 openai")
        return value

    def report_payload(self) -> dict[str, str]:
        """返回适合写入报告的客户端摘要。"""
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "model": self.model,
        }


class LLMSetting(StrictBaseModel):
    """正文翻译可选模型客户端配置。"""

    default_client: str = Field(title="默认客户端名称", description="命令未指定时使用的客户端。")
    clients: list[LLMClientSetting] = Field(title="模型客户端列表")
    _active_client: LLMClientSetting = PrivateAttr()

    @model_validator(mode="after")
    def _validate_clients_and_select_default(self) -> "LLMSetting":
        """校验客户端集合并选中默认客户端。"""
        if not self.clients:
            raise ValueError("llm.clients 至少需要配置一个模型客户端")
        names = [client.name for client in self.clients]
        duplicate_names = sorted({name for name in names if names.count(name) > 1})
        if duplicate_names:
            raise ValueError(f"llm.clients 存在重复客户端名称: {'、'.join(duplicate_names)}")
        self.select_active_client(None)
        return self

    @property
    def active_client(self) -> LLMClientSetting:
        """返回本次命令实际使用的模型客户端。"""
        return self._active_client

    @property
    def client_names(self) -> list[str]:
        """返回配置中的客户端名称列表。"""
        return [client.name for client in self.clients]

    @property
    def name(self) -> str:
        """返回本次命令实际使用的客户端名称。"""
        return self.active_client.name

    @property
    def provider_type(self) -> LLMProviderType:
        """返回本次命令实际使用的提供商类型。"""
        return self.active_client.provider_type

    @property
    def base_url(self) -> str:
        """返回本次命令实际使用的模型服务地址。"""
        return self.active_client.base_url

    @property
    def api_key(self) -> str:
        """返回本次命令实际使用的 API Key。"""
        return self.active_client.api_key

    @property
    def model(self) -> str:
        """返回本次命令实际使用的模型名称。"""
        return self.active_client.model

    @property
    def timeout(self) -> int:
        """返回本次命令实际使用的请求超时秒数。"""
        return self.active_client.timeout

    @property
    def request_body_extra(self) -> LLMRequestBodyExtra:
        """返回本次命令实际使用的额外请求体参数。"""
        return self.active_client.request_body_extra

    def select_active_client(self, client_name: str | None) -> None:
        """按命令行选择或默认配置选中模型客户端。"""
        selected_name = client_name or self.default_client
        clients_by_name = {client.name: client for client in self.clients}
        selected_client = clients_by_name.get(selected_name)
        if selected_client is None:
            available = "、".join(sorted(clients_by_name)) or "无"
            if client_name is None:
                raise ValueError(
                    f"llm.default_client 指向的模型客户端不存在: {selected_name}；可用客户端: {available}"
                )
            raise ValueError(
                f"命令指定的模型客户端不存在: {selected_name}；可用客户端: {available}"
            )
        self._active_client = selected_client

    def active_client_report(self) -> dict[str, str]:
        """返回本次命令所选客户端的报告摘要。"""
        return self.active_client.report_payload()


class TranslationContextSetting(StrictBaseModel):
    """正文切批上下文配置。"""

    token_size: int = Field(gt=0, title="每批 token 上限")
    factor: float = Field(gt=0, title="字符换算系数")
    max_command_items: int = Field(gt=0, title="连续命令上限")


class TextTranslationSetting(StrictBaseModel):
    """正文翻译阶段配置。"""

    worker_count: int = Field(gt=0, title="并发工作数")
    rpm: int | None = Field(default=None, gt=0, title="每分钟请求数")
    retry_count: int = Field(ge=0, title="请求重试次数")
    retry_delay: int = Field(ge=0, title="请求重试间隔")
    include_source_lines: bool = Field(default=False, title="模型输出原文对照")
    system_prompt_files: dict[SourceLanguage, str] = Field(title="按源语言选择的提示词文件")
    selected_system_prompt_file: str = Field(title="本次选中的提示词文件")
    system_prompt: str = Field(title="提示词内容")

    @field_validator("system_prompt_files")
    @classmethod
    def _validate_system_prompt_files(
        cls,
        value: dict[SourceLanguage, str],
    ) -> dict[SourceLanguage, str]:
        """日文和英文提示词文件必须在配置中显式声明。"""
        missing_languages = SUPPORTED_SOURCE_LANGUAGES.difference(value)
        if missing_languages:
            missing_label = "、".join(sorted(missing_languages))
            raise ValueError(f"text_translation.system_prompt_files 缺少源语言: {missing_label}")
        for source_language, prompt_file in value.items():
            if not prompt_file.strip():
                raise ValueError(f"text_translation.system_prompt_files.{source_language} 不能为空")
        return value


type EventCommandCode = Annotated[int, Field(ge=0, strict=True)]
REQUIRED_EVENT_COMMAND_ENGINE_KINDS: frozenset[EngineKind] = frozenset(("mv", "mz"))


class EventCommandTextSetting(StrictBaseModel):
    """事件指令参数外部规则配置。"""

    default_command_codes_by_engine: dict[EngineKind, list[EventCommandCode]] = Field(
        title="按引擎区分的默认事件指令编码",
    )

    @field_validator("default_command_codes_by_engine")
    @classmethod
    def _validate_default_command_codes_by_engine(
        cls,
        value: dict[EngineKind, list[int]],
    ) -> dict[EngineKind, list[int]]:
        """按引擎配置的事件指令编码必须覆盖 MV/MZ 且逐项非空。"""
        missing_engine_kinds = sorted(REQUIRED_EVENT_COMMAND_ENGINE_KINDS.difference(value))
        if missing_engine_kinds:
            missing_label = "、".join(missing_engine_kinds)
            raise ValueError(f"event_command_text.default_command_codes_by_engine 缺少引擎: {missing_label}")
        normalized_map: dict[EngineKind, list[int]] = {}
        for engine_kind, command_codes in value.items():
            normalized_map[engine_kind] = normalize_event_command_codes(
                command_codes,
                context=f"event_command_text.default_command_codes_by_engine.{engine_kind}",
            )
        return normalized_map

    def default_codes_for_engine(self, engine_kind: EngineKind) -> list[int]:
        """按引擎返回默认事件指令编码。"""
        return list(self.default_command_codes_by_engine[engine_kind])


def normalize_event_command_codes(value: list[int], *, context: str) -> list[int]:
    """校验并去重事件指令编码数组。"""
    if not value:
        raise ValueError(f"{context} 不能为空")

    normalized_codes: list[int] = []
    seen_codes: set[int] = set()
    for command_code in value:
        if command_code in seen_codes:
            continue
        normalized_codes.append(command_code)
        seen_codes.add(command_code)
    return normalized_codes


class WriteBackSetting(StrictBaseModel):
    """游戏文件写回阶段配置。"""

    replacement_font_path: str | None = Field(default=None, title="用户确认覆盖字体后使用的候选字体路径")


type RuntimeRustThreads = Literal["auto"] | Annotated[int, Field(gt=0, strict=True)]


class RuntimeSetting(StrictBaseModel):
    """Rust 原生核心运行时配置。"""

    rust_threads: RuntimeRustThreads = Field(
        default="auto",
        title="Rust 原生线程数",
        description="auto 使用 Rayon 默认线程数；正整数使用局部线程池限制并发。",
    )


type DebugLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
type DebugTimingDetailLevel = Literal["standard"]


class DebugLoggingSetting(StrictBaseModel):
    """debug 模式下的日志输出配置。"""

    enabled: bool = Field(default=True, title="是否启用 debug 日志")
    console_level: DebugLogLevel = Field(default="DEBUG", title="debug 终端日志等级")
    file_level: DebugLogLevel = Field(default="DEBUG", title="debug 文件日志等级")


class DebugTimingsSetting(StrictBaseModel):
    """debug 模式下的统一计时诊断配置。"""

    enabled: bool = Field(default=True, title="是否启用统一计时诊断")
    write_file: bool = Field(default=True, title="是否写出完整诊断 JSON 文件")
    include_summary_in_report: bool = Field(default=True, title="是否在 stdout 报告中追加诊断摘要")
    detail_level: DebugTimingDetailLevel = Field(default="standard", title="计时诊断详细程度")


class DebugLLMMessagesSetting(StrictBaseModel):
    """debug 模式下的 LLM 消息观测配置。"""

    enabled: bool = Field(default=True, title="是否启用 LLM 消息观测")
    output_dir: str = Field(default="output/debug/llm-messages", title="LLM 消息观测输出目录")


class DebugSetting(StrictBaseModel):
    """项目 debug 配置域。"""

    enabled: bool = Field(default=False, title="是否进入 debug 模式")
    logging: DebugLoggingSetting = Field(default_factory=DebugLoggingSetting, title="debug 日志配置")
    timings: DebugTimingsSetting = Field(default_factory=DebugTimingsSetting, title="debug 计时配置")
    llm_messages: DebugLLMMessagesSetting = Field(
        default_factory=DebugLLMMessagesSetting,
        title="debug LLM 消息观测配置",
    )


class TextRulesSetting(StrictBaseModel):
    """可配置的文本判断规则。"""

    source_language: SourceLanguage = Field(default=DEFAULT_SOURCE_LANGUAGE, title="源语言")
    source_residual_label: str = Field(default="日文", title="源文残留展示名称")
    strip_wrapping_punctuation_pairs: list[tuple[str, str]] = Field(
        default_factory=lambda: [("「", "」")],
        title="提取时剥离的成对标点",
    )
    preserve_wrapping_punctuation_pairs: list[tuple[str, str]] = Field(
        default_factory=lambda: [("「", "」"), ("『", "』")],
        title="译文必须按源文保留的成对包裹标点",
    )
    source_residual_allowed_chars: list[str] = Field(
        default_factory=lambda: ["っ", "ッ", "ー", "・", "。", "～", "…"]
    )
    source_residual_allowed_tail_chars: list[str] = Field(
        default_factory=lambda: [
            "あ",
            "い",
            "う",
            "え",
            "お",
            "っ",
            "ッ",
            "ん",
            "ー",
            "よ",
            "ね",
            "な",
            "か",
        ]
    )
    line_split_punctuations: list[str] = Field(
        default_factory=lambda: [
            "，",
            "。",
            "、",
            "；",
            "：",
            "！",
            "？",
            "…",
            "～",
            "—",
            "♪",
            "♡",
            "）",
            "】",
            "」",
            "』",
            ",",
            ".",
            ";",
            ":",
            "!",
            "?",
        ]
    )
    long_text_line_width_limit: int = Field(default=26, gt=0)
    line_width_count_pattern: str = Field(default=r"\S")
    source_text_required_pattern: str = Field(default=r"[ぁ-んァ-ヶ一-龯ー]+")
    source_text_exclusion_profile: SourceTextExclusionProfile = Field(default="none")
    source_residual_segment_pattern: str = Field(default=r"[ぁ-んァ-ヶー]+")
    allowed_source_residual_terms: list[str] = Field(default_factory=list)
    source_residual_terms_ignore_case: bool = Field(default=False)
    source_residual_detection_profile: SourceResidualDetectionProfile = Field(default="japanese_strict")
    english_source_copy_min_words: int = Field(default=4, gt=0)
    english_source_copy_min_letters: int = Field(default=12, gt=0)
    residual_escape_sequence_pattern: str = Field(default=r"\\[nrt]")


class Setting(StrictBaseModel):
    """项目运行时总配置。"""

    llm: LLMSetting = Field(title="正文模型服务配置")
    translation_context: TranslationContextSetting = Field(title="正文切批配置")
    text_translation: TextTranslationSetting = Field(title="正文翻译配置")
    event_command_text: EventCommandTextSetting = Field(title="事件指令参数外部规则配置")
    write_back: WriteBackSetting = Field(default_factory=WriteBackSetting, title="写回配置")
    runtime: RuntimeSetting = Field(default_factory=RuntimeSetting, title="运行时配置")
    debug: DebugSetting = Field(default_factory=DebugSetting, title="debug 配置")
    text_rules: TextRulesSetting = Field(default_factory=TextRulesSetting, title="文本规则")


__all__: list[str] = [
    "EventCommandTextSetting",
    "DebugLogLevel",
    "DebugLLMMessagesSetting",
    "DebugLoggingSetting",
    "DebugSetting",
    "DebugTimingDetailLevel",
    "DebugTimingsSetting",
    "LLMClientSetting",
    "LLMProviderType",
    "LLMSetting",
    "RuntimeRustThreads",
    "RuntimeSetting",
    "Setting",
    "StrictBaseModel",
    "TextRulesSetting",
    "TextTranslationSetting",
    "TranslationContextSetting",
    "WriteBackSetting",
]
