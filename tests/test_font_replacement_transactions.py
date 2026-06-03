"""字体覆盖写回计划事务测试。"""

from pathlib import Path

from app.application.handler import build_runtime_write_plan
from app.native_write_plan import NativeWriteBackPlan, NativeWriteBackSummary


def test_runtime_write_plan_contains_font_copy_and_css_operations_without_writing(tmp_path: Path) -> None:
    """字体复制和 gamefont.css 改写必须作为写回计划操作，不能提前写入。"""
    content_root = tmp_path / "game"
    fonts_dir = content_root / "fonts"
    fonts_dir.mkdir(parents=True)
    _ = (fonts_dir / "OldFont.woff").write_bytes(b"old font")
    css_path = fonts_dir / "gamefont.css"
    original_css = "@font-face { font-family: GameFont; src: url('OldFont.woff'); }\n"
    _ = css_path.write_text(original_css, encoding="utf-8")
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    native_plan = NativeWriteBackPlan(
        files=[],
        plugin_source_runtime_write_maps=[],
        font_replacement_records=[],
        summary=NativeWriteBackSummary(
            data_item_count=0,
            plugin_item_count=0,
            terminology_written_count=0,
            target_font_name=replacement_font.name,
            source_font_count=1,
            replaced_font_reference_count=0,
            font_copied=True,
            planned_file_count=0,
            skipped_file_count=0,
        ),
        timings_ms={"total": 1},
    )

    runtime_plan, css_replaced_count = build_runtime_write_plan(
        native_plan=native_plan,
        content_root=content_root,
        source_font_path=replacement_font,
    )

    operation_targets = [operation.target_path for operation in runtime_plan.file_operations]
    assert operation_targets == [
        fonts_dir / replacement_font.name,
        fonts_dir / "gamefont_origin.css",
        fonts_dir / "gamefont.css",
    ]
    assert css_replaced_count == 1
    assert len(runtime_plan.font_replacement_records) == 1
    assert not (fonts_dir / replacement_font.name).exists()
    assert not (fonts_dir / "gamefont_origin.css").exists()
    assert css_path.read_text(encoding="utf-8") == original_css
