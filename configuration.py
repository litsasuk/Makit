"""顶层 JSON 配置文件加载。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"配置文件不存在：{path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件 JSON 格式错误：{exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象")
    return config
