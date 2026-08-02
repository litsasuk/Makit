"""HTTP 请求头的规范化和不可变集合操作。"""

from __future__ import annotations

import re


HEADER_NAME_PATTERN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


def normalize_request_header(raw_value: str) -> str:
    value = raw_value.strip()
    if not value or len(value) > 8192:
        raise ValueError("请求头不能为空且不能超过 8192 个字符")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise ValueError("请求头不能包含换行符或 NUL 字符")
    if ":" not in value:
        raise ValueError("请求头格式应为 Name: Value")
    name, header_value = value.split(":", 1)
    name = name.strip()
    header_value = header_value.strip()
    if HEADER_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("请求头名称不合法")
    if not header_value:
        raise ValueError("请求头值不能为空")
    return f"{name}: {header_value}"


def replace_request_header(
    headers: tuple[str, ...], new_header: str
) -> tuple[str, ...]:
    new_name = new_header.split(":", 1)[0].strip().lower()
    retained = tuple(
        header
        for header in headers
        if header.split(":", 1)[0].strip().lower() != new_name
    )
    return (*retained, new_header)


def remove_request_header(
    headers: tuple[str, ...], name: str
) -> tuple[str, ...]:
    normalized_name = name.strip().lower()
    if normalized_name in {"all", "*"}:
        return ()
    if HEADER_NAME_PATTERN.fullmatch(name.strip()) is None:
        raise ValueError("请求头名称不合法")
    retained = tuple(
        header
        for header in headers
        if header.split(":", 1)[0].strip().lower() != normalized_name
    )
    if len(retained) == len(headers):
        raise ValueError(f"请求头未设置：{name}")
    return retained
