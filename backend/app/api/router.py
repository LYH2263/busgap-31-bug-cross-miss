from fastapi import APIRouter
from app.api import arrivals, lines, reports, trips
api_router = APIRouter()

@api_router.get("/health")
def health():
    return {"status": "ok"}

api_router.include_router(lines.router)
api_router.include_router(trips.router)
api_router.include_router(arrivals.router)
api_router.include_router(reports.router)
