"""正文翻译批次模型。"""

from dataclasses import dataclass

from app.llm.schemas import ChatMessage
from app.rmmz.schema import TranslationItem


@dataclass(slots=True)
class TranslationBatch:
    """一次模型请求需要处理的正文条目与消息列表。"""

    items: list[TranslationItem]
    prompt_ids_by_location_path: dict[str, str]
    messages: list[ChatMessage]


__all__: list[str] = ["TranslationBatch"]
