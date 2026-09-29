from datetime import datetime, timedelta
from app.services.bunch_engine import classify_gap, detect_bunching

def test_classify_bunching():
    assert classify_gap(2.0, 8.0, 3.0, 15.0)[0] == "bunching"

def test_classify_large():
    assert classify_gap(16.0, 8.0, 3.0, 15.0)[0] == "large_gap"

def test_classify_normal():
    assert classify_gap(8.0, 8.0, 3.0, 15.0)[0] == "normal"

def test_detect_bunching_events():
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=2)},
        {"stop_name": "A", "trip_no": "T3", "actual_arrive": base + timedelta(minutes=20)},
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0)
    assert len(events) == 2
    assert events[0].status == "bunching"
    assert events[1].status == "large_gap"

L1, L2 = 1, 2

def _arr(stop, trip, minute, line_id, code):
    return {"stop_name": stop, "trip_no": trip,
            "actual_arrive": datetime(2026, 1, 1, 8, 0) + timedelta(minutes=minute),
            "line_id": line_id, "line_code": code}

def test_shared_stop_merges_other_line_and_tags_counterpart():
    arrivals = [
        _arr("市民中心", "T1", 0, L1, "B12"),
        _arr("市民中心", "K1", 2, L2, "B13"),   # 跨线串车，对方 B13
        _arr("市民中心", "T2", 20, L1, "B12"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names={"市民中心"}, report_line_id=L1)
    assert len(events) == 2
    assert events[0].cross_line is True
    assert events[0].other_line_code == "B13"
    assert events[0].status == "bunching"
    # K1(2) -> T2(20)：本线车在后，对方仍是 B13
    assert events[1].cross_line is True
    assert events[1].other_line_code == "B13"

def test_intra_line_events_still_reported_at_shared_stop():
    arrivals = [
        _arr("市民中心", "T1", 0, L1, "B12"),
        _arr("市民中心", "T2", 2, L1, "B12"),   # 本线内部串车保留
        _arr("市民中心", "K1", 10, L2, "B13"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names={"市民中心"}, report_line_id=L1)
    intra = [e for e in events if not e.cross_line]
    assert len(intra) == 1
    assert intra[0].earlier_trip == "T1" and intra[0].later_trip == "T2"
    assert intra[0].status == "bunching"

def test_non_shared_stop_only_checks_report_line():
    arrivals = [
        _arr("火车站", "T1", 0, L1, "B12"),
        _arr("火车站", "K1", 1, L2, "B13"),   # 其它线到站必须被忽略
        _arr("火车站", "T2", 9, L1, "B12"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names={"市民中心"}, report_line_id=L1)
    assert len(events) == 1
    assert events[0].cross_line is False
    assert events[0].earlier_trip == "T1" and events[0].later_trip == "T2"

def test_no_default_cross_line_without_registration():
    # 即使传入了其它线路到站，只要站名未登记为共用站，就不做跨线判定
    arrivals = [
        _arr("市民中心", "T1", 0, L1, "B12"),
        _arr("市民中心", "K1", 2, L2, "B13"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names=set(), report_line_id=L1)
    assert all(e.cross_line is False for e in events)
    assert len(events) == 0

def test_intra_and_cross_pairs_coexist_at_shared_stop():
    # 本线短间隔与跨线对必须同时在，不能互相冲掉
    arrivals = [
        _arr("火车站", "T1", 0, L1, "B12"),
        _arr("火车站", "T2", 2, L1, "B12"),   # 本线串车
        _arr("火车站", "K1", 10, L2, "B13"),  # 跨线（本线在前）
        _arr("火车站", "T3", 12, L1, "B12"),  # 跨线（本线在后，对方仍是 B13）
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names={"火车站"}, report_line_id=L1)
    intra = [e for e in events if not e.cross_line]
    cross = [e for e in events if e.cross_line]
    assert len(intra) == 1
    assert (intra[0].earlier_trip, intra[0].later_trip) == ("T1", "T2")
    assert len(cross) == 2
    assert all(e.other_line_code == "B13" for e in cross)
    assert {(e.earlier_trip, e.later_trip) for e in cross} == {("T2", "K1"), ("K1", "T3")}
    # 建议句与事件字段使用同一套对方线号
    assert all("B13" in e.suggestion for e in cross)

def test_cross_never_tagged_as_own_line_code():
    arrivals = [
        _arr("火车站", "K1", 0, L2, "B13"),
        _arr("火车站", "T1", 2, L1, "B12"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names={"火车站"}, report_line_id=L1)
    assert len(events) == 1
    assert events[0].cross_line is True
    assert events[0].other_line_code == "B13"
    assert "B12" not in events[0].suggestion.split("】")[0]

def test_cross_merge_failure_keeps_events_already_emitted():
    # 前一站正常产出；问题站外线数据损坏导致归并失败时，退化为只跑本线，已写出事件不被清空
    good = [
        _arr("起点站", "T1", 0, L1, "B12"),
        _arr("起点站", "T2", 2, L1, "B12"),
    ]
    broken_foreign = {"stop_name": "火车站", "trip_no": "K1", "actual_arrive": None,
                      "line_id": L2, "line_code": "B13"}
    own_at_station = [
        _arr("火车站", "T3", 10, L1, "B12"),
        _arr("火车站", "T4", 12, L1, "B12"),
    ]
    events = detect_bunching(good + own_at_station + [broken_foreign], 8.0, 3.0, 15.0,
                             shared_stop_names={"火车站"}, report_line_id=L1)
    names = [(e.stop_name, e.earlier_trip, e.later_trip) for e in events]
    assert ("起点站", "T1", "T2") in names          # 已写出事件保留
    assert ("火车站", "T3", "T4") in names          # 问题站退化为本线检测
    assert all(not e.cross_line for e in events)

def test_no_shared_config_behaves_like_baseline():
    # 没配共用时跟底座一样：只按本线相邻到站判定
    arrivals = [
        _arr("A", "T1", 0, L1, "B12"),
        _arr("A", "K9", 1, L2, "B13"),
        _arr("A", "T2", 20, L1, "B12"),
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0,
                             shared_stop_names=set(), report_line_id=L1)
    assert len(events) == 1
    assert events[0].cross_line is False
    assert (events[0].earlier_trip, events[0].later_trip) == ("T1", "T2")
