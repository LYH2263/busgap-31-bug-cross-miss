from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Line, SharedStop
router = APIRouter(prefix="/lines", tags=["lines"])

class SharedStopIn(BaseModel):
    stop_name: str

def _line_or_404(db: Session, line_id: int) -> Line:
    line = db.get(Line, line_id)
    if not line:
        raise HTTPException(404, "线路不存在")
    return line

def _serialize(line: Line) -> dict:
    return {"id": line.id, "code": line.code, "name": line.name,
            "planned_headway_min": line.planned_headway_min,
            "bunch_threshold": line.bunch_threshold, "large_threshold": line.large_threshold,
            "shared_stops": sorted(s.stop_name for s in line.shared_stops)}

@router.get("")
def list_lines(db: Session = Depends(get_db)):
    rows = db.scalars(select(Line).order_by(Line.id)).all()
    return [_serialize(r) for r in rows]

@router.post("/{line_id}/shared-stops")
def add_shared_stop(line_id: int, body: SharedStopIn, db: Session = Depends(get_db)):
    line = _line_or_404(db, line_id)
    stop_name = body.stop_name.strip()
    if not stop_name:
        raise HTTPException(400, "站名不能为空")
    shared = db.scalars(select(SharedStop).where(SharedStop.stop_name == stop_name)).first()
    if shared is None:
        shared = SharedStop(stop_name=stop_name)
        db.add(shared)
    if not any(s.id == shared.id for s in line.shared_stops):
        line.shared_stops.append(shared)
    db.commit()
    db.refresh(line)
    return _serialize(line)

@router.delete("/{line_id}/shared-stops/{stop_name}")
def remove_shared_stop(line_id: int, stop_name: str, db: Session = Depends(get_db)):
    line = _line_or_404(db, line_id)
    shared = db.scalars(select(SharedStop).where(SharedStop.stop_name == stop_name)).first()
    if shared is not None:
        line.shared_stops = [s for s in line.shared_stops if s.id != shared.id]
        db.flush()
        db.refresh(shared)
        # 没有任何线路登记时清掉该共用站
        if not shared.lines:
            db.delete(shared)
    db.commit()
    db.refresh(line)
    return _serialize(line)
