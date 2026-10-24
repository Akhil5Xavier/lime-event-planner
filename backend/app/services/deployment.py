"""Scooter deployment recommendations.

The model is deliberately simple and transparent so managers can sanity-check it:

  attendance  = manager override > API estimate > venue capacity x fill factor > category default
  scooters    = ceil(daily attendance x scooter_share), capped per spot
  windows     = arrival (90 min before start) and departure (60 min after end)

Events whose venues are within `hotspot_radius_m` of each other are grouped
into one hotspot; its need is the peak of overlapping events, not the plain
sum, because scooters freed after one event can serve the next.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.geo import haversine_m
from app.models import Event
from app.services.events import effective_end, local_days

FILL_FACTOR = {
    "sport": 0.9,
    "concert": 0.8,
    "theatre": 0.75,
    "festival": 0.6,
    "expo": 0.5,
    "conference": 0.5,
    "film": 0.5,
    "community": 0.4,
    "other": 0.5,
}
DEFAULT_ATTENDANCE = {
    "sport": 3000,
    "concert": 1500,
    "theatre": 500,
    "festival": 10000,
    "expo": 5000,
    "conference": 800,
    "film": 200,
    "community": 500,
    "other": 300,
}
ARRIVAL_LEAD = timedelta(minutes=90)
DEPARTURE_TAIL = timedelta(minutes=60)
# Daily operating hours assumed for the middle days of multi-day events.
MULTIDAY_OPEN = time(11, 0)
MULTIDAY_CLOSE = time(23, 0)
HIGH_ATTENDANCE = 10_000
MEDIUM_ATTENDANCE = 2_000
PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Window:
    kind: str  # arrival | departure
    start: datetime
    end: datetime


@dataclass
class Recommendation:
    event_id: int
    attendance: int
    attendance_source: str  # manual | api | capacity | default
    extra_scooters: int
    priority: str
    windows: list[Window]

    @property
    def span(self) -> tuple[datetime, datetime]:
        return self.windows[0].start, self.windows[-1].end


@dataclass
class Hotspot:
    name: str
    lat: float
    lng: float
    extra_scooters: int
    priority: str
    venue_ids: list[int] = field(default_factory=list)
    event_ids: list[int] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)


def estimate_attendance(event: Event) -> tuple[int, str]:
    if event.attendance_override:
        return event.attendance_override, "manual"
    if event.expected_attendance:
        return event.expected_attendance, "api"
    category = event.category if event.category in FILL_FACTOR else "other"
    if event.venue is not None and event.venue.capacity:
        return round(event.venue.capacity * FILL_FACTOR[category]), "capacity"
    return DEFAULT_ATTENDANCE[category], "default"


def priority_for(attendance: int) -> str:
    if attendance >= HIGH_ATTENDANCE:
        return "high"
    if attendance >= MEDIUM_ATTENDANCE:
        return "medium"
    return "low"


def recommend(event: Event, day: date, settings: Settings) -> Recommendation:
    tz = ZoneInfo(settings.timezone)
    days = local_days(event, tz)
    attendance, source = estimate_attendance(event)
    # API/manual estimates for multi-day events are totals; spread them over the days.
    # Capacity-based estimates are already per day.
    daily = attendance
    if len(days) > 1 and source in ("api", "manual"):
        daily = math.ceil(attendance / len(days))

    start, end = event.start_at, effective_end(event)
    open_at = start if start.astimezone(tz).date() == day else datetime.combine(day, MULTIDAY_OPEN, tz)
    close_at = end if end.astimezone(tz).date() == day else datetime.combine(day, MULTIDAY_CLOSE, tz)
    windows = [
        Window("arrival", open_at - ARRIVAL_LEAD, open_at),
        Window("departure", close_at, close_at + DEPARTURE_TAIL),
    ]
    scooters = min(math.ceil(daily * settings.scooter_share), settings.max_scooters_per_spot)
    return Recommendation(
        event_id=event.id,
        attendance=daily,
        attendance_source=source,
        extra_scooters=scooters,
        priority=priority_for(daily),
        windows=windows,
    )


def peak_concurrent(recs: list[Recommendation]) -> int:
    """Largest number of scooters needed at the same moment across overlapping events."""
    points = []
    for r in recs:
        start, end = r.span
        points += [(start, r.extra_scooters), (end, -r.extra_scooters)]
    # At equal times, process ends before starts so back-to-back events don't stack.
    points.sort(key=lambda p: (p[0], p[1]))
    running = peak = 0
    for _, delta in points:
        running += delta
        peak = max(peak, running)
    return peak


def build_hotspots(
    events: list[Event], recs: dict[int, Recommendation], settings: Settings
) -> list[Hotspot]:
    """Group events by venue proximity into hotspots, biggest first."""
    located = [e for e in events if e.venue is not None]
    located.sort(key=lambda e: recs[e.id].extra_scooters, reverse=True)

    groups: list[tuple[Event, list[Event]]] = []  # (anchor, members)
    for e in located:
        for anchor, members in groups:
            if haversine_m(anchor.venue.lat, anchor.venue.lng, e.venue.lat, e.venue.lng) <= settings.hotspot_radius_m:
                members.append(e)
                break
        else:
            groups.append((e, [e]))

    hotspots = []
    for anchor, members in groups:
        member_recs = [recs[m.id] for m in members]
        need = peak_concurrent(member_recs)
        venue_ids = sorted({m.venue.id for m in members})
        hotspots.append(
            Hotspot(
                name=anchor.venue.name if len(venue_ids) == 1 else f"{anchor.venue.name} area",
                lat=anchor.venue.lat,
                lng=anchor.venue.lng,
                extra_scooters=min(need, settings.max_scooters_per_spot),
                priority=max((r.priority for r in member_recs), key=PRIORITY_RANK.__getitem__),
                venue_ids=venue_ids,
                event_ids=[m.id for m in members],
                windows=sorted((w for r in member_recs for w in r.windows), key=lambda w: w.start),
            )
        )
    hotspots.sort(key=lambda h: (PRIORITY_RANK[h.priority], h.extra_scooters), reverse=True)
    return hotspots
