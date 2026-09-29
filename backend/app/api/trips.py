from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Trip
router = APIRouter(prefix="/trips", tags=["trips"])

@router.get("")
def list_trips(line_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Trip).order_by(Trip.planned_depart)
    if line_id is not None: q = q.where(Trip.line_id == line_id)
    return [{"id": r.id, "line_id": r.line_id, "trip_no": r.trip_no,
             "planned_depart": r.planned_depart.isoformat(), "vehicle_no": r.vehicle_no}
            for r in db.scalars(q).all()]
