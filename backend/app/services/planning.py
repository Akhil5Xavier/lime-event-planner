"""Day- and range-level planning shared by the REST API and the AI assistant's tools.

Raises ValueError for bad input; callers turn that into an HTTP 422 or a tool error.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CATEGORIES, Event
from app.services.deployment import PRIORITY_RANK, Hotspot, Recommendation, build_hotspots, recommend
from app.services.events import day_bounds, events_between, local_days

MAX_RANGE_DAYS = 100


@dataclass
class DayTotals:
    event_count: int
    total_attendance: int
    extra_scooters: int
    priority: str | None


def parse_categories(category: str | None) -> list[str] | None:
    """'sport,concert' -> ['sport', 'concert']; None or '' -> None (all categories)."""
    if not category:
        return None
    cats = [c.strip() for c in category.split(",") if c.strip()]
    unknown = set(cats) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"Unknown category: {', '.join(sorted(unknown))}")
    return cats


def events_in_local_range(db: Session, start: date, end: date, category: str | None, tz: ZoneInfo) -> list[Event]:
    """Primary events running between two Stuttgart dates, end exclusive."""
    if end <= start:
        raise ValueError("end must be after start")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"Range is limited to {MAX_RANGE_DAYS} days")
    range_start, _ = day_bounds(start, tz)
    range_end, _ = day_bounds(end, tz)
    return events_between(db, range_start, range_end, parse_categories(category))


def events_by_day(db: Session, start: date, end: date, category: str | None, tz: ZoneInfo) -> dict[date, list[Event]]:
    """Events grouped by each local day they run on (multi-day events appear on every day)."""
    by_day: dict[date, list[Event]] = defaultdict(list)
    for e in events_in_local_range(db, start, end, category, tz):
        for d in local_days(e, tz):
            if start <= d < end:
                by_day[d].append(e)
    return dict(sorted(by_day.items()))


def summarize_day(
    events: list[Event], day: date, settings: Settings
) -> tuple[dict[int, Recommendation], list[Hotspot], DayTotals]:
    recs = {e.id: recommend(e, day, settings) for e in events}
    hotspots = build_hotspots(events, recs, settings)
    unlocated = sum(recs[e.id].extra_scooters for e in events if e.venue is None)
    totals = DayTotals(
        event_count=len(events),
        total_attendance=sum(r.attendance for r in recs.values()),
        extra_scooters=sum(h.extra_scooters for h in hotspots) + unlocated,
        priority=max((r.priority for r in recs.values()), key=PRIORITY_RANK.__getitem__, default=None),
    )
    return recs, hotspots, totals
