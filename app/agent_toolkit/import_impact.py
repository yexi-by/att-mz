"""规则和术语导入后的连锁影响报告字段。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rmmz.text_rules import JsonArray, JsonObject


@dataclass(frozen=True, slots=True)
class ImportImpact:
    """导入命令对后续流程的影响摘要。"""

    requires_doctor: bool
    requires_text_index_rebuild: bool
    write_back_probe_affected: bool
    deleted_translation_count: int = 0
    deleted_translation_backup_path: str = ""
    review_recheck_domains: tuple[str, ...] = ()
    terminology_write_back_affected: bool = False

    def summary_fields(self) -> JsonObject:
        """生成稳定 summary 字段。"""
        review_domains: JsonArray = [domain for domain in self.review_recheck_domains]
        return {
            "impact_requires_doctor": self.requires_doctor,
            "impact_requires_text_index_rebuild": self.requires_text_index_rebuild,
            "impact_write_back_probe_affected": self.write_back_probe_affected,
            "impact_deleted_translation_count": self.deleted_translation_count,
            "impact_deleted_translation_backup_path": self.deleted_translation_backup_path,
            "impact_review_recheck_domains": review_domains,
            "impact_terminology_write_back_affected": self.terminology_write_back_affected,
        }

    def detail_fields(self) -> JsonObject:
        """生成 details.import_impact 字段。"""
        return {
            "requires_doctor": self.requires_doctor,
            "requires_text_index_rebuild": self.requires_text_index_rebuild,
            "write_back_probe_affected": self.write_back_probe_affected,
            "deleted_translation_count": self.deleted_translation_count,
            "deleted_translation_backup_path": self.deleted_translation_backup_path,
            "review_recheck_domains": [domain for domain in self.review_recheck_domains],
            "terminology_write_back_affected": self.terminology_write_back_affected,
        }


def rule_import_impact(
    *,
    deleted_translation_count: int,
    deleted_translation_backup_path: str | None,
    review_recheck_domains: tuple[str, ...] = (),
) -> ImportImpact:
    """规则导入后的默认影响。"""
    return ImportImpact(
        requires_doctor=True,
        requires_text_index_rebuild=True,
        write_back_probe_affected=True,
        deleted_translation_count=deleted_translation_count,
        deleted_translation_backup_path=deleted_translation_backup_path or "",
        review_recheck_domains=review_recheck_domains,
    )


def terminology_import_impact() -> ImportImpact:
    """术语导入后的默认影响。"""
    return ImportImpact(
        requires_doctor=True,
        requires_text_index_rebuild=False,
        write_back_probe_affected=True,
        terminology_write_back_affected=True,
    )
