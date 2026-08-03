"""根据模式、目标和请求头安全渲染子进程参数。"""

from __future__ import annotations

from pathlib import Path

from tooling.models import TargetInput, TestMode, Tool
from tooling.targets import host_from_target


def _mode(tool: Tool, mode_id: str) -> TestMode:
    for mode in tool.modes:
        if mode.id == mode_id:
            return mode
    raise ValueError(f"工具 {tool.id!r} 不支持测试方式：{mode_id}")


def build_arguments(
    tool: Tool,
    mode_id: str,
    target: TargetInput | None,
    output_dir: Path,
    headers: tuple[str, ...] = (),
) -> list[str]:
    """安全渲染配置参数；返回值直接传给 subprocess，不经过 Shell。"""
    mode = _mode(tool, mode_id)
    replacements = {
        "output_dir": str(output_dir),
    }

    arguments = mode.arguments
    if mode.requires_url:
        if target is None:
            raise ValueError(f"工具 {tool.id!r} 的 {mode.id!r} 方式需要 URL")
        primary_target = target.urls[0]
        replacements.update(
            {
                "url": primary_target,
                "host": host_from_target(primary_target),
            }
        )
        if not target.is_list:
            if mode.url_arguments is None:
                raise ValueError(f"工具 {tool.id!r} 的 {mode.id!r} 方式不接受 URL")
            arguments = mode.url_arguments
    if mode.requires_url and target is not None and target.is_list:
        if mode.url_file_arguments is None:
            raise ValueError(f"工具 {tool.id!r} 的 {mode.id!r} 方式不支持 TXT 列表")
        normalized_target_file = output_dir / "targets.txt"
        normalized_target_file.write_text(
            "\n".join(target.urls) + "\n", encoding="utf-8"
        )
        hosts = tuple(dict.fromkeys(host_from_target(url) for url in target.urls))
        normalized_host_file = output_dir / "hosts.txt"
        normalized_host_file.write_text("\n".join(hosts) + "\n", encoding="utf-8")
        replacements.update(
            {
                "url_file": str(normalized_target_file),
                "host_file": str(normalized_host_file),
            }
        )
        arguments = mode.url_file_arguments

    rendered: list[str] = []
    for argument in arguments:
        value = argument
        for name, replacement in replacements.items():
            value = value.replace("{" + name + "}", replacement)
        rendered.append(value)

    for header in headers:
        name, value = header.split(":", 1)
        header_template = tool.header_arguments
        header_replacements = {"header": header, "cookie": value.strip()}
        if name.strip().lower() == "cookie" and header_template is None:
            header_template = tool.cookie_arguments
        if header_template is None:
            raise ValueError(f"工具 {tool.id!r} 不支持自定义请求头")
        for argument in header_template:
            rendered_argument = argument
            for placeholder, replacement in header_replacements.items():
                rendered_argument = rendered_argument.replace(
                    "{" + placeholder + "}", replacement
                )
            rendered.append(rendered_argument)
    return rendered
