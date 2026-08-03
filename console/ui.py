"""Makit 控制台颜色辅助函数，不介入外部工具的输出流。"""

from __future__ import annotations

import ctypes
import os
import sys
import unicodedata
from typing import TextIO


RESET = "\033[0m"
BOLD_CYAN = "1;36"
BOLD_MAGENTA = "1;35"
BOLD_RED = "1;31"
BOLD_WHITE = "1;37"
BLUE = "34"
GREEN = "32"
YELLOW = "33"
MODULE_SECTION_YELLOW = "93"
RED = "31"
DIM = "2"


def _supports_color(stream: TextIO) -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name != "nt":
        return True

    # Windows 10+ 需要为控制台句柄启用虚拟终端序列。
    try:
        handle_id = -12 if stream is sys.stderr else -11
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(handle_id)
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


def colorize(text: object, code: str, stream: TextIO | None = None) -> str:
    output = stream or sys.stdout
    value = str(text)
    if not _supports_color(output):
        return value
    return f"\033[{code}m{value}{RESET}"


def title(text: object) -> str:
    return colorize(text, BOLD_CYAN)


def heading(text: object) -> str:
    return colorize(text, BOLD_CYAN)


def banner(text: object) -> str:
    return colorize(text, BOLD_MAGENTA)


class _Coord(ctypes.Structure):
    _fields_ = [
        ("X", ctypes.c_short),
        ("Y", ctypes.c_short),
    ]


class _SmallRect(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short),
        ("Top", ctypes.c_short),
        ("Right", ctypes.c_short),
        ("Bottom", ctypes.c_short),
    ]


class _ConsoleScreenBufferInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", _Coord),
        ("dwCursorPosition", _Coord),
        ("wAttributes", ctypes.c_ushort),
        ("srWindow", _SmallRect),
        ("dwMaximumWindowSize", _Coord),
    ]


def _console_text_width(value: str) -> int:
    width = 0
    for character in value:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def _cursor_for_cell(value: str, target_cell: int) -> int:
    consumed = 0
    for index, character in enumerate(value):
        character_width = _console_text_width(character)
        if consumed + character_width > target_cell:
            return index
        consumed += character_width
    return len(value)


def _move_vertical_cursor(
    value: str,
    cursor: int,
    prompt_width: int,
    line_width: int,
    direction: int,
) -> int:
    """按控制台的一行宽度移动光标，不读取命令历史。"""
    current_cell = prompt_width + _console_text_width(value[:cursor])
    last_cell = prompt_width + _console_text_width(value)
    target_cell = current_cell + direction * max(1, line_width)
    target_cell = max(prompt_width, min(last_cell, target_cell))
    return _cursor_for_cell(value, target_cell - prompt_width)


def _read_windows_editable_line(prompt: str, initial_value: str) -> str:
    """用控制台坐标安全重绘可跨行编辑的 Windows 长命令。"""
    import msvcrt

    if any(character in initial_value for character in ("\x00", "\r", "\n")):
        raise ValueError("命令初始值不能包含 NUL 或换行字符")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_std_handle = kernel32.GetStdHandle
    get_std_handle.argtypes = [ctypes.c_ulong]
    get_std_handle.restype = ctypes.c_void_p
    get_screen_info = kernel32.GetConsoleScreenBufferInfo
    get_screen_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ConsoleScreenBufferInfo),
    ]
    get_screen_info.restype = ctypes.c_int
    set_cursor_position = kernel32.SetConsoleCursorPosition
    set_cursor_position.argtypes = [ctypes.c_void_p, _Coord]
    set_cursor_position.restype = ctypes.c_int

    output_handle = get_std_handle(ctypes.c_ulong(-11).value)
    if output_handle in {None, ctypes.c_void_p(-1).value}:
        raise ctypes.WinError(ctypes.get_last_error())

    def screen_info() -> _ConsoleScreenBufferInfo:
        value = _ConsoleScreenBufferInfo()
        if not get_screen_info(output_handle, ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def set_cursor(x: int, y: int) -> None:
        if not set_cursor_position(output_handle, _Coord(x, y)):
            raise ctypes.WinError(ctypes.get_last_error())

    initial_info = screen_info()
    origin_x = initial_info.dwCursorPosition.X
    origin_y = initial_info.dwCursorPosition.Y
    characters = list(initial_value)
    cursor = len(characters)
    prompt_width = _console_text_width(prompt)
    previous_cells = 0
    colored = _supports_color(sys.stdout)

    def redraw() -> None:
        nonlocal origin_y, previous_cells
        content = "".join(characters)
        current_cells = prompt_width + _console_text_width(content)
        written_cells = max(current_cells, previous_cells)
        current_info = screen_info()
        line_width = max(1, current_info.dwSize.X)
        buffer_height = max(1, current_info.dwSize.Y)

        set_cursor(origin_x, origin_y)
        if colored:
            sys.stdout.write(
                f"\033[{BOLD_RED}m{prompt}\033[{BOLD_WHITE}m{content}{RESET}"
            )
        else:
            sys.stdout.write(prompt + content)
        if previous_cells > current_cells:
            sys.stdout.write(" " * (previous_cells - current_cells))
        sys.stdout.flush()

        final_row = origin_y + (origin_x + written_cells) // line_width
        if final_row >= buffer_height:
            origin_y = max(0, origin_y - (final_row - buffer_height + 1))

        cursor_cells = prompt_width + _console_text_width(content[:cursor])
        cursor_offset = origin_x + cursor_cells
        set_cursor(cursor_offset % line_width, origin_y + cursor_offset // line_width)
        previous_cells = current_cells

    redraw()
    while True:
        character = msvcrt.getwch()
        if character in {"\r", "\n"}:
            cursor = len(characters)
            redraw()
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(characters)
        if character == "\x03":
            raise KeyboardInterrupt
        if character == "\x1a" and not characters:
            raise EOFError
        if character in {"\x00", "\xe0"}:
            key = msvcrt.getwch()
            if key == "K" and cursor > 0:  # Left
                cursor -= 1
            elif key == "M" and cursor < len(characters):  # Right
                cursor += 1
            elif key in {"H", "P"}:  # Up / Down，不使用控制台命令历史。
                cursor = _move_vertical_cursor(
                    "".join(characters),
                    cursor,
                    prompt_width,
                    screen_info().dwSize.X,
                    -1 if key == "H" else 1,
                )
            elif key == "G":  # Home
                cursor = 0
            elif key == "O":  # End
                cursor = len(characters)
            elif key == "S" and cursor < len(characters):  # Delete
                del characters[cursor]
            redraw()
            continue
        if character in {"\b", "\x7f"}:
            if cursor > 0:
                cursor -= 1
                del characters[cursor]
                redraw()
            continue
        if character == "\x01":  # Ctrl+A
            cursor = 0
            redraw()
            continue
        if character == "\x05":  # Ctrl+E
            cursor = len(characters)
            redraw()
            continue
        if character == "\x15":  # Ctrl+U
            del characters[:cursor]
            cursor = 0
            redraw()
            continue
        if character >= " ":
            characters.insert(cursor, character)
            cursor += 1
            redraw()


def read_console_input(prompt: object, initial_value: str | None = None) -> str:
    """读取控制台输入；可提供能够直接修改的初始文本。"""
    value = str(prompt)
    if (
        initial_value is not None
        and sys.stdin.isatty()
        and os.name == "nt"
    ):
        return _read_windows_editable_line(value, initial_value)

    startup_hook_set = False
    readline_module = None
    if initial_value is not None and sys.stdin.isatty():
        try:
            import readline as readline_module

            readline_module.set_startup_hook(
                lambda: readline_module.insert_text(initial_value)
            )
            startup_hook_set = True
        except ImportError:
            readline_module = None

    if not _supports_color(sys.stdout):
        try:
            result = input(value)
        finally:
            if startup_hook_set and readline_module is not None:
                readline_module.set_startup_hook()
    else:
        sys.stdout.write(
            f"\033[{BOLD_RED}m{value}\033[{BOLD_WHITE}m"
        )
        sys.stdout.flush()
        try:
            result = input("")
        finally:
            if startup_hook_set and readline_module is not None:
                readline_module.set_startup_hook()
            sys.stdout.write(RESET)
            sys.stdout.flush()

    if not sys.stdin.isatty():
        print()
        if initial_value is not None and not result.strip():
            return initial_value
    return result


def info(text: object) -> str:
    return colorize(text, BLUE)


def success(text: object) -> str:
    return colorize(text, GREEN)


def warning(text: object) -> str:
    return colorize(text, YELLOW)


def module_section_title(text: object) -> str:
    return colorize(text, MODULE_SECTION_YELLOW)


def error(text: object, stream: TextIO | None = None) -> str:
    return colorize(text, RED, stream)


def muted(text: object) -> str:
    return colorize(text, DIM)
