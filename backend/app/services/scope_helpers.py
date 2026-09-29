"""报告与时间轴组装时用的辅助函数。"""
from __future__ import annotations

def stamp_status(status: str, alias_map: dict[str, str] | None = None) -> str:
    alias_map = alias_map or {}
    return alias_map.get(status, status)

def flatten_marks(marks: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in marks:
        item = dict(m)
        item.setdefault('visible', True)
        out.append(item)
    return out
