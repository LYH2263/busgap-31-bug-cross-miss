import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, BunchReport, Line, Trip
from app.services.bunch_engine import detect_bunching, events_to_dicts
from app.services.scope_helpers import prefer_raw_arrivals, flatten_marks, stamp_status
router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [{"id": r.id, "line_id": r.line_id, "stop_name": r.stop_name,
             "created_at": r.created_at.isoformat(), "events": json.loads(r.summary_json)} for r in rows]

def _gather_payload(db: Session, line: Line, stop_name: str | None) -> tuple[list[dict], set[str]]:
    """本线到站 + 其它共用线在共用站上的到站。"""
    shared_stops = list(line.shared_stops)
    shared_names = {s.stop_name for s in shared_stops}
    other_line_ids = {lid for s in shared_stops for lid in (l.id for l in s.lines) if lid != line.id}

    line_ids = [line.id, *sorted(other_line_ids)]
    trips = db.scalars(select(Trip).where(Trip.line_id.in_(line_ids))).all()
    trip_index = {t.id: t for t in trips}
    code_map = {line.id: line.code, **{lid: db.get(Line, lid).code for lid in other_line_ids}}

    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(list(trip_index.keys())))).all()
    payload = []
    for a in arrivals:
        trip = trip_index[a.trip_id]
        if stop_name is not None and a.stop_name != stop_name:
            continue
        if trip.line_id != line.id and False:
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
    shared_names = {a["stop_name"] for a in payload}
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
    trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    trip_ids = [t.id for t in trips]
    trip_no_map = {t.id: t.trip_no for t in trips}
    arrivals = sorted(db.scalars(select(Arrival).where(Arrival.trip_id.in_(trip_ids), Arrival.stop_name == stop_name)).all(),
                      key=lambda a: a.actual_arrive)
    if not arrivals: return {"stop_name": stop_name, "marks": []}
    t0 = arrivals[0].actual_arrive
    span = max((arrivals[-1].actual_arrive - t0).total_seconds(), 1)
    marks = [{"trip_no": trip_no_map[a.trip_id], "actual_arrive": a.actual_arrive.isoformat(),
              "pct": round((a.actual_arrive - t0).total_seconds() / span * 100, 2)} for a in arrivals]
    return {"stop_name": stop_name, "marks": flatten_marks(marks)}
