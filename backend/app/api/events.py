import uuid
from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import CATEGORIES, Event, User, Venue
from app.schemas import (
    AttendanceOverrideIn,
    CalendarDayOut,
    DayEventOut,
    DayOut,
    DaySummary,
    EventIn,
    EventOut,
    EventUpdate,
    HotspotOut,
    RecommendationOut,
)
from app.security import get_current_user
from app.services.deployment import PRIORITY_RANK, build_hotspots, recommend
from app.services.events import day_bounds, events_between, local_days

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_current_user)])

MAX_RANGE_DAYS = 100


def _categories(category: str | None) -> list[str] | None:
    if not category:
        return None
    cats = [c.strip() for c in category.split(",") if c.strip()]
    unknown = set(cats) - set(CATEGORIES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown category: {', '.join(sorted(unknown))}")
    return cats


def _range(db: Session, start: date, end: date, category: str | None, tz: ZoneInfo) -> list[Event]:
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Range is limited to {MAX_RANGE_DAYS} days")
    range_start, _ = day_bounds(start, tz)
    range_end, _ = day_bounds(end, tz)
    return events_between(db, range_start, range_end, _categories(category))


def _summarize(events: list[Event], day: date, settings: Settings):
    recs = {e.id: recommend(e, day, settings) for e in events}
    hotspots = build_hotspots(events, recs, settings)
    unlocated = sum(recs[e.id].extra_scooters for e in events if e.venue is None)
    summary = DaySummary(
        event_count=len(events),
        total_attendance=sum(r.attendance for r in recs.values()),
        extra_scooters=sum(h.extra_scooters for h in hotspots) + unlocated,
        priority=max((r.priority for r in recs.values()), key=PRIORITY_RANK.__getitem__, default=None),
    )
    return recs, hotspots, summary


@router.get("", response_model=list[EventOut])
def list_events(
    start: date,
    end: date,
    category: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Events running between two local dates (end exclusive), e.g. a calendar month."""
    return _range(db, start, end, category, ZoneInfo(settings.timezone))


@router.get("/summary", response_model=list[CalendarDayOut])
def calendar_summary(
    start: date,
    end: date,
    category: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Per-day event count, attendance and scooter need, for colouring calendar cells."""
    tz = ZoneInfo(settings.timezone)
    by_day: dict[date, list[Event]] = defaultdict(list)
    for e in _range(db, start, end, category, tz):
        for d in local_days(e, tz):
            if start <= d < end:
                by_day[d].append(e)
    out = []
    for d in sorted(by_day):
        _, _, summary = _summarize(by_day[d], d, settings)
        out.append(CalendarDayOut(date=d, **summary.model_dump()))
    return out


@router.get("/day/{day}", response_model=DayOut)
def day_view(
    day: date,
    category: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Everything a manager needs for one day: events, per-event recommendation and hotspots."""
    events = _range(db, day, day + timedelta(days=1), category, ZoneInfo(settings.timezone))
    recs, hotspots, summary = _summarize(events, day, settings)
    return DayOut(
        date=day,
        events=[
            DayEventOut(
                **EventOut.model_validate(e).model_dump(),
                recommendation=RecommendationOut.model_validate(recs[e.id]),
            )
            for e in events
        ],
        hotspots=[HotspotOut.model_validate(h) for h in hotspots],
        summary=summary,
    )


def _get_event(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _require_manual(event: Event) -> None:
    if not event.is_manual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imported events are overwritten on the next sync; only the attendance override can be changed.",
        )


def _check_venue(db: Session, venue_id: int | None) -> None:
    if venue_id is not None and db.get(Venue, venue_id) is None:
        raise HTTPException(status_code=422, detail="Unknown venue_id")


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return _get_event(db, event_id)


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.end_at and body.end_at <= body.start_at:
        raise HTTPException(status_code=422, detail="end_at must be after start_at")
    venue_id = body.venue_id
    if body.new_venue is not None:
        venue = Venue(**body.new_venue.model_dump())
        db.add(venue)
        db.flush()
        venue_id = venue.id
    _check_venue(db, venue_id)
    event = Event(
        source="manual",
        external_id=uuid.uuid4().hex,
        is_manual=True,
        venue_id=venue_id,
        created_by_id=user.id,
        updated_by_id=user.id,
        **body.model_dump(exclude={"venue_id", "new_venue"}),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    event = _get_event(db, event_id)
    _require_manual(event)
    changes = body.model_dump(exclude_unset=True)
    if "venue_id" in changes:
        _check_venue(db, changes["venue_id"])
    for key, value in changes.items():
        setattr(event, key, value)
    event.updated_by_id = user.id
    if event.end_at and event.end_at <= event.start_at:
        raise HTTPException(status_code=422, detail="end_at must be after start_at")
    db.commit()
    db.refresh(event)
    return event


@router.put("/{event_id}/attendance", response_model=EventOut)
def set_attendance_override(event_id: int, body: AttendanceOverrideIn, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """Managers' own attendance estimate; works for imported events too and survives re-syncs."""
    event = _get_event(db, event_id)
    event.attendance_override = body.attendance_override
    event.updated_by_id = user.id
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = _get_event(db, event_id)
    _require_manual(event)
    db.delete(event)
    db.commit()
