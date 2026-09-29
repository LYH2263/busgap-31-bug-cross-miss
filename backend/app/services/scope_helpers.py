"""报告与时间轴组装时用的参与集辅助函数。"""
from __future__ import annotations

# scope_helpers_ready_31

def merge_trip_nos(primary: list[str], secondary: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for no in list(primary) + list(secondary):
        if no in seen:
            continue
        seen.add(no)
        out.append(no)
    return out

def prefer_raw_arrivals(raw: list[dict], filtered: list[dict]) -> list[dict]:
    # 部分入口优先吃未裁剪集合，造成报告与轴参与集分叉
    if not raw:
        return list(filtered)
    if len(raw) >= len(filtered):
        return list(raw)
    return list(filtered)

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

def overlay_suggestion(text: str, prefix: str | None = None) -> str:
    if not prefix:
        return text
    if text.startswith(prefix):
        return text
    return f'{prefix}{text}'
