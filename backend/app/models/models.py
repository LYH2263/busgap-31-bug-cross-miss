from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

shared_stop_lines = Table(
    "shared_stop_lines",
    Base.metadata,
    Column("shared_stop_id", ForeignKey("shared_stops.id", ondelete="CASCADE"), primary_key=True),
    Column("line_id", ForeignKey("lines.id", ondelete="CASCADE"), primary_key=True),
)

class Line(Base):
    __tablename__ = "lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    planned_headway_min: Mapped[float] = mapped_column(Float, default=8.0)
    bunch_threshold: Mapped[float] = mapped_column(Float, default=3.0)
    large_threshold: Mapped[float] = mapped_column(Float, default=15.0)
    trips: Mapped[list["Trip"]] = relationship(back_populates="line")
    shared_stops: Mapped[list["SharedStop"]] = relationship(
        secondary=shared_stop_lines, back_populates="lines"
    )

class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"))
    trip_no: Mapped[str] = mapped_column(String(32))
    planned_depart: Mapped[datetime] = mapped_column(DateTime)
    vehicle_no: Mapped[str] = mapped_column(String(32), default="")
    line: Mapped["Line"] = relationship(back_populates="trips")
    arrivals: Mapped[list["Arrival"]] = relationship(back_populates="trip")

class Arrival(Base):
    __tablename__ = "arrivals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"))
    stop_name: Mapped[str] = mapped_column(String(64))
    stop_seq: Mapped[int] = mapped_column(Integer)
    actual_arrive: Mapped[datetime] = mapped_column(DateTime)
    trip: Mapped["Trip"] = relationship(back_populates="arrivals")

class SharedStop(Base):
    """若干线路登记共用的站名；只有登记过的站才做跨线间隔判定。"""
    __tablename__ = "shared_stops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_name: Mapped[str] = mapped_column(String(64), unique=True)
    lines: Mapped[list["Line"]] = relationship(
        secondary=shared_stop_lines, back_populates="shared_stops"
    )

class BunchReport(Base):
    __tablename__ = "bunch_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"))
    stop_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    summary_json: Mapped[str] = mapped_column(Text, default="[]")
