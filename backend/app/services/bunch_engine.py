"""Bus bunching: planned headway vs actual arrival gaps.

共用站（shared stops）可由多条线路登记：只有登记过的站才把本线与其它共用线的
到站并入同一时间序做相邻间隔判定，跨线相邻对会标注对方线路代号。
- 共用站上本线内部的相邻对同样保留，跨线归并不冲掉本线短间隔；
- 非共用站只对本线班次做判定，即使 payload 里混入了其它线到站；
- 单个站的跨线归并失败时，退化为该站只跑本线，此前已写出的事件不清空。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class GapEvent:
    stop_name: str
    earlier_trip: str
    later_trip: str
    gap_min: float
    planned_headway_min: float
    status: str
    suggestion: str
    cross_line: bool = False
    other_line_code: str | None = None


def classify_gap(gap_min: float, planned_headway_min: float, bunch_threshold: float, large_threshold: float) -> tuple[str, str]:
    if gap_min < bunch_threshold:
        return ("bunching", f"间隔 {gap_min:.1f} 分钟低于串车阈值 {bunch_threshold}，建议后车缓行或抽稀。")
    if gap_min > large_threshold:
        return ("large_gap", f"间隔 {gap_min:.1f} 分钟超过大间隔阈值 {large_threshold}，建议前车减速或加发。")
    return ("normal", f"间隔接近计划 {planned_headway_min:.1f} 分钟，保持即可。")


def _sort_key(x: dict):
    return (x["actual_arrive"], x["line_id"] or 0, x["trip_no"])


def _emit_pairs(
    stop: str,
    candidates: list[dict],
    planned_headway_min: float,
    bunch_threshold: float,
    large_threshold: float,
    report_line_id,
) -> list[GapEvent]:
    """对已按到站时间排好序的候选序列逐对判定；跨线对标注对方（非报告线）线号。"""
    out: list[GapEvent] = []
    for i in range(1, len(candidates)):
        prev, cur = candidates[i - 1], candidates[i]
        gap_min = (cur["actual_arrive"] - prev["actual_arrive"]).total_seconds() / 60.0
        status, suggestion = classify_gap(gap_min, planned_headway_min, bunch_threshold, large_threshold)
        cross = prev["line_id"] != cur["line_id"]
        other_code = None
        if cross:
            # 对方线 = 相邻对里不属于报告线的一方；报告线为空时取前车一侧。
            if report_line_id is not None:
                foreign = cur if prev["line_id"] == report_line_id else prev
            else:
                foreign = prev
            other_code = foreign.get("line_code") or None
            suggestion = f"【跨线·对方 {other_code or ''}】{suggestion}"
        out.append(GapEvent(
            stop, prev["trip_no"], cur["trip_no"], round(gap_min, 2),
            planned_headway_min, status, suggestion,
            cross_line=cross, other_line_code=other_code,
        ))
    return out


def detect_bunching(
    arrivals: list[dict],
    planned_headway_min: float,
    bunch_threshold: float,
    large_threshold: float,
    shared_stop_names: set[str] | None = None,
    report_line_id=None,
) -> list[GapEvent]:
    shared_stop_names = set(shared_stop_names or set())
    # 未标注线路的到站视为本线班次（保持旧调用兼容）
    for a in arrivals:
        a.setdefault("line_id", report_line_id)
        a.setdefault("line_code", None)

    by_stop: dict[str, list[dict]] = {}
    for a in arrivals:
        by_stop.setdefault(a["stop_name"], []).append(a)

    events: list[GapEvent] = []
    for stop, items in by_stop.items():
        try:
            # 只有声明过的共用站才并入外线；非共用站候选只留本线。
            if report_line_id is not None and stop not in shared_stop_names:
                candidates = [a for a in items if a["line_id"] == report_line_id]
            else:
                candidates = list(items)
            candidates.sort(key=_sort_key)
            # 整站结果算好后再并入，避免归并中途失败留下半截事件。
            stop_events = _emit_pairs(
                stop, candidates, planned_headway_min,
                bunch_threshold, large_threshold, report_line_id,
            )
        except Exception:
            # 跨线归并失败：该站退化为只跑本线；此前各站已写出的事件不动。
            own = [a for a in items if report_line_id is None or a["line_id"] == report_line_id]
            own.sort(key=_sort_key)
            stop_events = _emit_pairs(
                stop, own, planned_headway_min,
                bunch_threshold, large_threshold, report_line_id,
            )
        events.extend(stop_events)
    return events


def events_to_dicts(events: list[GapEvent]) -> list[dict]:
    return [asdict(e) for e in events]
