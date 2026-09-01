"""通用工具：id / 时间戳 / JSON 列处理。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dumps(value) -> str:
    """dict/list → JSON 字符串（SQLite 列）。"""
    return json.dumps(value, ensure_ascii=False)


def loads(raw, default=None):
    """JSON 字符串 → Python 对象；空/非法返回默认值。"""
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default
