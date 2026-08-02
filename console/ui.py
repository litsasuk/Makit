"""Makit 控制台颜色辅助函数，不介入外部工具的输出流。"""

from __future__ import annotations

import ctypes
import os
import sys
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


def read_console_input(prompt: object) -> str:
    """以高亮红色显示提示符，并以高亮白色显示用户输入。"""
    value = str(prompt)
    if not _supports_color(sys.stdout):
        result = input(value)
    else:
        sys.stdout.write(
            f"\033[{BOLD_RED}m{value}\033[{BOLD_WHITE}m"
        )
        sys.stdout.flush()
        try:
            result = input("")
        finally:
            sys.stdout.write(RESET)
            sys.stdout.flush()

    if not sys.stdin.isatty():
        print()
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
