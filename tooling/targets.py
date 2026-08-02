"""目标 URL 规范化、校验和 TXT 列表加载。"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

from tooling.models import TargetInput


MAX_TARGET_FILE_SIZE = 10 * 1024 * 1024
MAX_TARGET_COUNT = 100_000
PLAIN_HTTP_PORTS = frozenset({80, 8000, 8080, 8888})


def validate_target(raw_target: str) -> str:
    target = raw_target.strip()
    if not target:
        raise ValueError("目标 URL 不能为空")
    if len(target) > 2048 or any(char.isspace() for char in target):
        raise ValueError("目标 URL 不能包含空白字符且长度不能超过 2048")

    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("请输入以 http:// 或 https:// 开头的有效 URL")
    if parsed.username or parsed.password:
        raise ValueError("目标 URL 不应包含用户名或密码")
    if "\\" in target:
        raise ValueError("目标 URL 不能包含反斜杠")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("目标 URL 的端口不合法") from exc

    hostname = parsed.hostname
    assert hostname is not None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.rstrip(".").encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("目标 URL 的主机名不合法") from exc
        labels = ascii_hostname.split(".")
        if (
            len(ascii_hostname) > 253
            or any(not label or len(label) > 63 for label in labels)
            or any(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
                is None
                for label in labels
            )
        ):
            raise ValueError("目标 URL 的主机名不合法")
    return target


def normalize_target(raw_target: str) -> str:
    """校验目标 URL，并为裸域名或主机地址补全协议。"""
    target = raw_target.strip()
    if not target:
        raise ValueError("目标 URL 不能为空")
    if target.lower().startswith(("http://", "https://")):
        return validate_target(target)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target):
        raise ValueError("目标 URL 只支持 http:// 或 https:// 协议")

    authority_and_path = target[2:] if target.startswith("//") else target
    parsed = urlsplit(f"//{authority_and_path}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("目标 URL 的端口不合法") from exc
    scheme = "http" if port in PLAIN_HTTP_PORTS else "https"
    return validate_target(f"{scheme}://{authority_and_path}")


def host_from_target(target: str) -> str:
    hostname = urlsplit(target).hostname
    if not hostname:
        raise ValueError("URL 中缺少主机名")
    return hostname


def load_target_input(raw_value: str, project_dir: Path) -> TargetInput:
    """将用户输入解析为单 URL、裸域名或 UTF-8 TXT URL 列表。"""
    value = raw_value.strip()
    if value.lower().startswith(("http://", "https://")) or value.startswith("//"):
        url = normalize_target(value)
        return TargetInput("url", url, (url,))
    if not value:
        raise ValueError("目标 URL 或 TXT 文件不能为空")

    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        current_candidate = (Path.cwd() / candidate).resolve()
        project_candidate = (project_dir / candidate).resolve()
        candidate = current_candidate if current_candidate.is_file() else project_candidate
    else:
        candidate = candidate.resolve()

    if not candidate.is_file():
        looks_like_file = (
            candidate.suffix.lower() == ".txt"
            and (
                "/" not in value
                or "\\" in value
                or value.startswith(("./", "../", "/"))
            )
        )
        if looks_like_file:
            raise ValueError(f"URL 列表不存在：{candidate}")
        url = normalize_target(value)
        return TargetInput("url", url, (url,))
    if candidate.suffix.lower() != ".txt":
        raise ValueError("URL 列表文件的扩展名必须为 .txt")
    if candidate.stat().st_size > MAX_TARGET_FILE_SIZE:
        raise ValueError("URL 列表不能超过 10 MiB")

    try:
        lines = candidate.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("URL 列表必须使用 UTF-8 编码") from exc

    urls: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        try:
            url = normalize_target(item)
        except ValueError as exc:
            raise ValueError(f"URL 列表第 {line_number} 行无效：{exc}") from exc
        if url not in seen:
            urls.append(url)
            seen.add(url)
        if len(urls) > MAX_TARGET_COUNT:
            raise ValueError("URL 列表不能超过 100000 个目标")
    if not urls:
        raise ValueError("URL 列表中没有有效目标")
    return TargetInput("file", str(candidate), tuple(urls), candidate)
