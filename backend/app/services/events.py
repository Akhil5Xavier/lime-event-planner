from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Event

# Used when an event has no end time.
DEFAULT_DURATION = timedelta(hours=3)


def effective_end(event: Event) -> datetime:
    return event.end_at or event.start_at + DEFAULT_DURATION


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC-comparable [start, end) of a local calendar day."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)


def local_days(event: Event, tz: ZoneInfo) -> list[date]:
    """Local dates the event is running on (an event ending exactly at midnight doesn't count the next day)."""
    first = event.start_at.astimezone(tz).date()
    last = (effective_end(event) - timedelta(microseconds=1)).astimezone(tz).date()
    last = max(first, last)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def events_between(
    db: Session,
    start: datetime,
    end: datetime,
    categories: list[str] | None = None,
) -> list[Event]:
    """Primary (non-duplicate) events running at any point in [start, end)."""
    stmt = (
        select(Event)
        .options(joinedload(Event.venue), joinedload(Event.created_by), joinedload(Event.updated_by))
        .where(
            Event.duplicate_of_id.is_(None),
            Event.start_at < end,
            or_(
                Event.end_at > start,
                (Event.end_at.is_(None)) & (Event.start_at > start - DEFAULT_DURATION),
            ),
        )
        .order_by(Event.start_at)
    )
    if categories:
        stmt = stmt.where(Event.category.in_(categories))
    return list(db.scalars(stmt).unique())
