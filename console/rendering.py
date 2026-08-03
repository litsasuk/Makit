"""CJK 对齐的通用表格渲染。"""

from __future__ import annotations

import unicodedata

from console.ui import heading, module_section_title, title as title_style


def display_width(value: str) -> int:
    """返回终端显示宽度，避免中文字符导致表格列错位。"""
    width = 0
    for character in value:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
    return width


def pad_cell(value: str, width: int) -> str:
    return value + " " * max(0, width - display_width(value))


def table_widths(
    headers: tuple[str, ...], rows: list[tuple[object, ...]]
) -> tuple[int, ...]:
    text_rows = [tuple(str(value) for value in row) for row in rows]
    return tuple(
        max(
            [
                display_width(header),
                *(display_width(row[index]) for row in text_rows),
            ]
        )
        for index, header in enumerate(headers)
    )


def show_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
    widths: tuple[int, ...] | None = None,
) -> None:
    """以 msfconsole 风格渲染标题和左对齐表格。"""
    text_rows = [tuple(str(value) for value in row) for row in rows]
    widths = widths or table_widths(headers, rows)
    indent = "    "
    is_module_list = (
        title == "Operation Modes"
        or title == "Modules"
        or title.endswith(" Modules")
    )
    is_mode_list = title.startswith("Modes (") and title.endswith(")")
    render_title = module_section_title if is_module_list else title_style
    print(render_title(title))
    if not (is_module_list or is_mode_list):
        print(render_title("=" * display_width(title)))
    print(
        heading(
            indent
            + "  ".join(
                pad_cell(header, widths[i]) for i, header in enumerate(headers)
            )
        )
    )
    print(
        heading(
            indent
            + "  ".join(
                pad_cell("-" * display_width(header), widths[i])
                for i, header in enumerate(headers)
            )
        )
    )
    for row in text_rows:
        print(indent + "  ".join(pad_cell(value, widths[i]) for i, value in enumerate(row)))
