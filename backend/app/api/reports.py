import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, BunchReport, Line, SharedStop, Trip
from app.services.bunch_engine import detect_bunching, events_to_dicts
from app.services.scope_helpers import flatten_marks, stamp_status
router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [{"id": r.id, "line_id": r.line_id, "stop_name": r.stop_name,
             "created_at": r.created_at.isoformat(), "events": json.loads(r.summary_json)} for r in rows]

def _shared_scope(db: Session, line: Line) -> tuple[set[str], set[int]]:
    """每次检测都现读数据库：拿刚保存的共用名单与登记在线的对方线路，禁止沿用改前缓存。"""
    shared_stops = list(line.shared_stops)
    shared_names = {s.stop_name for s in shared_stops}
    other_line_ids = {
        lid
        for s in shared_stops
        for lid in (l.id for l in s.lines)
        if lid != line.id
    }
    return shared_names, other_line_ids

def _gather_payload(db: Session, line: Line, stop_name: str | None) -> tuple[list[dict], set[str]]:
    """本线全部到站 + 其它共用线【仅在声明共用站上】的到站。"""
    shared_names, other_line_ids = _shared_scope(db, line)

    line_ids = [line.id, *sorted(other_line_ids)]
    trips = db.scalars(select(Trip).where(Trip.line_id.in_(line_ids))).all()
    trip_index = {t.id: t for t in trips}
    code_lines = db.scalars(select(Line).where(Line.id.in_(line_ids))).all()
    code_map = {l.id: l.code for l in code_lines}

    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(list(trip_index.keys())))).all()
    payload = []
    for a in arrivals:
        trip = trip_index[a.trip_id]
        if stop_name is not None and a.stop_name != stop_name:
            continue
        # 非共用站只放本线：对方线到站即使存在也不进跨线池。
        if trip.line_id != line.id and a.stop_name not in shared_names:
            continue
        payload.append({"stop_name": a.stop_name, "trip_no": trip.trip_no,
                        "actual_arrive": a.actual_arrive,
                        "line_id": trip.line_id, "line_code": code_map[trip.line_id]})
    return payload, shared_names

@router.post("/run")
def run_detection(line_id: int, stop_name: str | None = None, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    payload, shared_names = _gather_payload(db, line, stop_name)
    events = detect_bunching(payload, line.planned_headway_min, line.bunch_threshold, line.large_threshold,
                             shared_stop_names=shared_names, report_line_id=line_id)
    data = events_to_dicts(events)
    data = [{**e, 'status': stamp_status(e.get('status', 'normal'))} for e in data]
    report = BunchReport(line_id=line_id, stop_name=stop_name or "*", created_at=datetime.utcnow(),
                         summary_json=json.dumps(data, ensure_ascii=False))
    db.add(report); db.commit(); db.refresh(report)
    return {"id": report.id, "events": data}

@router.get("/suggestions")
def suggestions(line_id: int, db: Session = Depends(get_db)):
    result = run_detection(line_id=line_id, stop_name=None, db=db)
    return {"line_id": line_id, "suggestions": [e for e in result["events"] if e["status"] != "normal"]}

@router.get("/timeline")
def timeline(line_id: int, stop_name: str = "市民中心", db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    shared_names, _ = _shared_scope(db, line)

    def _marks_from(trip_rows: list[Trip]) -> list[dict]:
        trip_index = {t.id: t for t in trip_rows}
        arrivals = db.scalars(
            select(Arrival).where(
                Arrival.trip_id.in_(list(trip_index.keys())),
                Arrival.stop_name == stop_name,
            )
        ).all()
        arrivals = sorted(arrivals, key=lambda a: a.actual_arrive)
        if not arrivals:
            return []
        t0 = arrivals[0].actual_arrive
        span = max((arrivals[-1].actual_arrive - t0).total_seconds(), 1)
        return [{
            "trip_no": trip_index[a.trip_id].trip_no,
            "line_code": trip_index[a.trip_id].line.code,
            "cross_line": trip_index[a.trip_id].line_id != line_id,
            "actual_arrive": a.actual_arrive.isoformat(),
            "pct": round((a.actual_arrive - t0).total_seconds() / span * 100, 2),
        } for a in arrivals]

    own_trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    own_marks = _marks_from(own_trips)
    if not own_marks:
        return {"stop_name": stop_name, "marks": []}

    marks = own_marks
    # 只有该站在刚保存的共用名单里，才把登记对方线路的轴点并入；归并失败则保留本线轴点。
    if stop_name in shared_names:
        try:
            shared = db.scalars(select(SharedStop).where(SharedStop.stop_name == stop_name)).first()
            other_ids = [l.id for l in shared.lines if l.id != line_id] if shared else []
            if other_ids:
                other_trips = db.scalars(select(Trip).where(Trip.line_id.in_(other_ids))).all()
                merged = _marks_from(own_trips + other_trips)
                if merged:
                    marks = merged
        except Exception:
            marks = own_marks

    return {"stop_name": stop_name, "marks": flatten_marks(marks)}
