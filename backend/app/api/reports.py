import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, BunchReport, Line, Trip
from app.services.bunch_engine import detect_bunching, events_to_dicts
from app.services.scope_helpers import flatten_marks, stamp_status
router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [{"id": r.id, "line_id": r.line_id, "stop_name": r.stop_name,
             "created_at": r.created_at.isoformat(), "events": json.loads(r.summary_json)} for r in rows]

def _gather_payload(db: Session, line: Line, stop_name: str | None) -> tuple[list[dict], set[str]]:
    """本线到站 + 其它共用线在共用站上的到站。

    共用名单只取本线在「线路」页声明登记的集合，每次检测从 DB 现读，
    不接受 payload 里出现的其它站名，也不缓存改前名单。
    """
    shared_stops = list(line.shared_stops)
    shared_names = {s.stop_name for s in shared_stops}
    other_line_ids = {lid for s in shared_stops for lid in (l.id for l in s.lines) if lid != line.id}

    line_ids = [line.id, *sorted(other_line_ids)]
    trips = db.scalars(select(Trip).where(Trip.line_id.in_(line_ids))).all()
    trip_index = {t.id: t for t in trips}
    line_rows = db.scalars(select(Line).where(Line.id.in_(line_ids))).all()
    code_map = {r.id: r.code for r in line_rows}

    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(list(trip_index.keys())))).all()
    payload = []
    for a in arrivals:
        trip = trip_index[a.trip_id]
        if stop_name is not None and a.stop_name != stop_name:
            continue
        payload.append({"stop_name": a.stop_name, "trip_no": trip.trip_no,
                        "actual_arrive": a.actual_arrive,
                        "line_id": trip.line_id, "line_code": code_map[trip.line_id]})
    return payload, shared_names

def _status(data: list[dict]) -> list[dict]:
    return [{**e, 'status': stamp_status(e.get('status', 'normal'))} for e in data]

@router.post("/run")
def run_detection(line_id: int, stop_name: str | None = None, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    payload, shared_names = _gather_payload(db, line, stop_name)

    # 阶段一：本线事件。先落库，跨线归并失败也不清掉已写出的本线结果。
    base_events = detect_bunching(payload, line.planned_headway_min, line.bunch_threshold, line.large_threshold,
                                  shared_stop_names=None, report_line_id=line_id)
    report = BunchReport(line_id=line_id, stop_name=stop_name or "*", created_at=datetime.utcnow(),
                         summary_json=json.dumps(_status(events_to_dicts(base_events)), ensure_ascii=False))
    db.add(report); db.commit(); db.refresh(report)

    # 阶段二：共用站跨线归并（共用名单为本轮现读）。失败则保留阶段一结果。
    cross_merge_ok = True
    try:
        full_events = detect_bunching(payload, line.planned_headway_min, line.bunch_threshold, line.large_threshold,
                                      shared_stop_names=shared_names, report_line_id=line_id)
        data = _status(events_to_dicts(full_events))
        report.summary_json = json.dumps(data, ensure_ascii=False)
        db.commit(); db.refresh(report)
    except Exception:
        db.rollback()
        cross_merge_ok = False
        data = json.loads(report.summary_json)

    return {"id": report.id, "events": data, "cross_merge": cross_merge_ok}

@router.get("/suggestions")
def suggestions(line_id: int, db: Session = Depends(get_db)):
    result = run_detection(line_id=line_id, stop_name=None, db=db)
    return {"line_id": line_id, "suggestions": [e for e in result["events"] if e["status"] != "normal"]}

@router.get("/timeline")
def timeline(line_id: int, stop_name: str = "市民中心", db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    payload, shared_names = _gather_payload(db, line, stop_name)

    # 轴点：本线全部保留；跨线轴点只在共用站出现，对方线号与报告同一套。
    # 跨线归并失败不影响本线轴点。
    own = [a for a in payload if a["line_id"] == line_id]
    try:
        cross = [a for a in payload if a["line_id"] != line_id and a["stop_name"] in shared_names]
    except Exception:
        cross = []
    items = sorted(own + cross, key=lambda a: a["actual_arrive"])
    if not items: return {"stop_name": stop_name, "marks": []}
    t0 = items[0].actual_arrive
    span = max((items[-1].actual_arrive - t0).total_seconds(), 1)
    marks = [{"trip_no": a["trip_no"], "line_id": a["line_id"], "line_code": a["line_code"],
              "actual_arrive": a["actual_arrive"].isoformat(),
              "pct": round((a["actual_arrive"] - t0).total_seconds() / span * 100, 2),
              "cross_line": a["line_id"] != line_id} for a in items]
    return {"stop_name": stop_name, "marks": flatten_marks(marks)}
