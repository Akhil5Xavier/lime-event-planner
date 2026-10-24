from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


CATEGORIES = (
    "concert",
    "sport",
    "theatre",
    "festival",
    "expo",
    "conference",
    "film",
    "community",
    "other",
)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str | None] = mapped_column(String(500))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int | None] = mapped_column(Integer)
    # Pipe-separated alternative names used to match API venue names.
    aliases: Mapped[str | None] = mapped_column(Text)
    # Free text for ops, e.g. "Park scooters on Mercedesstraße, not the plaza".
    scooter_zone_note: Mapped[str | None] = mapped_column(Text)
    # "<source>:<id>" of the API venue this row was created from or matched to.
    external_ref: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="venue")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_event_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(50), default="other", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), index=True)
    expected_attendance: Mapped[int | None] = mapped_column(Integer)
    # Set by a manager; takes precedence over every other attendance estimate.
    attendance_override: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    # Points at the primary copy when another source already has this event.
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), index=True)
    # Who added (manual events) and who last changed the event; null for changes made by syncs.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", name="fk_events_created_by"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", name="fk_events_updated_by"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    venue: Mapped[Venue | None] = relationship(back_populates="events")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    updated_by: Mapped["User | None"] = relationship(foreign_keys=[updated_by_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="manager")  # admin | manager
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")  # schedule | manual | cli
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | success | failed
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
