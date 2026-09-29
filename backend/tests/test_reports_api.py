from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.models import Arrival, Line, SharedStop, Trip

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)

BASE = datetime(2026, 9, 17, 7, 0, 0)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_line(code, headway=8.0, bunch=3.0, large=15.0):
    db = TestingSessionLocal()
    line = Line(code=code, name=code, planned_headway_min=headway,
                bunch_threshold=bunch, large_threshold=large)
    db.add(line)
    db.commit()
    db.refresh(line)
    db.close()
    return line.id


def _add_trip(line_id, trip_no, offset, stops):
    db = TestingSessionLocal()
    trip = Trip(line_id=line_id, trip_no=trip_no, planned_depart=BASE + timedelta(minutes=offset),
                vehicle_no="X")
    db.add(trip)
    db.flush()
    for seq, stop in enumerate(stops):
        db.add(Arrival(trip_id=trip.id, stop_name=stop, stop_seq=seq,
                       actual_arrive=BASE + timedelta(minutes=offset + seq * 6)))
    db.commit()
    db.close()


def _add_arrival(line_id, trip_no, stop, minute):
    db = TestingSessionLocal()
    trip = Trip(line_id=line_id, trip_no=trip_no, planned_depart=BASE, vehicle_no="X")
    db.add(trip)
    db.flush()
    db.add(Arrival(trip_id=trip.id, stop_name=stop, stop_seq=0,
                   actual_arrive=BASE + timedelta(minutes=minute)))
    db.commit()
    db.close()


def _declare_shared(stop_name, line_ids):
    db = TestingSessionLocal()
    shared = SharedStop(stop_name=stop_name)
    db.add(shared)
    db.flush()
    for lid in line_ids:
        shared.lines.append(db.get(Line, lid))
    db.commit()
    db.close()


def test_run_keeps_both_intra_and_cross_pairs_with_consistent_code():
    b12 = _make_line("B12")
    b13 = _make_line("B13", headway=9.0, large=16.0)
    _add_arrival(b12, "T1", "火车站", 0)
    _add_arrival(b12, "T2", "火车站", 2)    # 本线串车
    _add_arrival(b13, "K1", "火车站", 10)  # 跨线
    _declare_shared("火车站", [b12, b13])

    res = client.post(f"/api/reports/run?line_id={b12}")
    assert res.status_code == 200
    events = res.json()["events"]
    intra = [e for e in events if not e["cross_line"]]
    cross = [e for e in events if e["cross_line"]]
    assert [(e["earlier_trip"], e["later_trip"]) for e in intra] == [("T1", "T2")]
    assert len(cross) == 1
    assert cross[0]["other_line_code"] == "B13"
    assert "对方 B13" in cross[0]["suggestion"]

    # 落库报告与建议句读出来必须是同一套线号
    stored = client.get("/api/reports").json()[0]["events"]
    assert [e for e in stored if e["cross_line"]][0]["other_line_code"] == "B13"
    tips = client.get(f"/api/reports/suggestions?line_id={b12}").json()["suggestions"]
    assert all(e["other_line_code"] == "B13" for e in tips if e["cross_line"])


def test_non_shared_stop_foreign_arrivals_never_enter_pool():
    b12 = _make_line("B12")
    b13 = _make_line("B13")
    _add_arrival(b12, "T1", "西站", 0)
    _add_arrival(b13, "K1", "西站", 1)   # 西站未登记共用
    _add_arrival(b12, "T2", "西站", 20)
    # 只登记另一个站，确保西站不在共用名单
    _declare_shared("市民中心", [b12, b13])

    events = client.post(f"/api/reports/run?line_id={b12}").json()["events"]
    west = [e for e in events if e["stop_name"] == "西站"]
    assert len(west) == 1
    assert west[0]["cross_line"] is False
    assert (west[0]["earlier_trip"], west[0]["later_trip"]) == ("T1", "T2")


def test_detection_recomputes_with_freshly_saved_shared_list():
    b12 = _make_line("B12")
    b13 = _make_line("B13")
    _add_arrival(b12, "T1", "火车站", 0)
    _add_arrival(b13, "K1", "火车站", 2)

    # 未登记：不出跨线
    events = client.post(f"/api/reports/run?line_id={b12}").json()["events"]
    assert all(not e["cross_line"] for e in events)

    # 在 B13 侧登记共用（模拟线路页刚保存的名单），必须立即按新名单重算
    _declare_shared("火车站", [b12, b13])
    events = client.post(f"/api/reports/run?line_id={b12}").json()["events"]
    cross = [e for e in events if e["cross_line"]]
    assert len(cross) == 1 and cross[0]["other_line_code"] == "B13"

    # 取消共用后再检，跨线立即消失（禁止沿用改前缓存）
    db = TestingSessionLocal()
    line = db.get(Line, b12)
    shared = db.query(SharedStop).filter_by(stop_name="火车站").first()
    line.shared_stops = [s for s in line.shared_stops if s.id != shared.id]
    db.commit()
    db.close()
    events = client.post(f"/api/reports/run?line_id={b12}").json()["events"]
    assert all(not e["cross_line"] for e in events)


def test_timeline_merges_counterpart_marks_only_at_declared_shared_stop():
    b12 = _make_line("B12")
    b13 = _make_line("B13")
    _add_arrival(b12, "T1", "火车站", 0)
    _add_arrival(b13, "K1", "火车站", 3)
    _add_arrival(b12, "T2", "火车站", 20)
    _add_arrival(b13, "K9", "西站", 1)
    _add_arrival(b12, "T9", "西站", 5)
    _declare_shared("火车站", [b12, b13])

    marks = client.get(f"/api/reports/timeline?line_id={b12}&stop_name=火车站").json()["marks"]
    trips = {(m["line_code"], m["trip_no"]) for m in marks}
    assert ("B12", "T1") in trips and ("B13", "K1") in trips and ("B12", "T2") in trips
    k1 = [m for m in marks if m["trip_no"] == "K1"][0]
    assert k1["line_code"] == "B13" and k1["cross_line"] is True
    assert [m for m in marks if not m["cross_line"]]  # 本线轴点仍在

    # 非共用站：对方轴点不并入，只有本线点
    west = client.get(f"/api/reports/timeline?line_id={b12}&stop_name=西站").json()["marks"]
    assert [(m["line_code"], m["trip_no"]) for m in west] == [("B12", "T9")]
    assert all(not m["cross_line"] for m in west)
