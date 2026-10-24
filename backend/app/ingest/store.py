"""Writes normalized events to the database: venue matching, upsert and cross-source dedupe."""

from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geo import haversine_m, normalize_name
from app.ingest.base import NormalizedEvent
from app.models import Event, Venue

VENUE_MATCH_RADIUS_M = 150
DUPLICATE_START_TOLERANCE = timedelta(hours=1)
DUPLICATE_TITLE_SIMILARITY = 0.6


@dataclass
class UpsertResult:
    created: int = 0
    updated: int = 0
    duplicates: int = 0


class VenueResolver:
    """Maps API venue info to a Venue row, creating one when nothing matches.

    Order: external ref, then name/alias, then a known venue within 150 m.
    Loads venues once per run so a run with thousands of events stays cheap.
    """

    def __init__(self, db: Session):
        self.db = db
        self.venues: list[Venue] = list(db.scalars(select(Venue)))

    def _names(self, v: Venue) -> list[str]:
        names = [v.name] + [a for a in (v.aliases or "").split("|") if a]
        return [n for n in map(normalize_name, names) if n]

    def resolve(self, ev: NormalizedEvent) -> Venue | None:
        if ev.venue_external_ref:
            for v in self.venues:
                if v.external_ref == ev.venue_external_ref:
                    return v

        if ev.venue_name:
            incoming = normalize_name(ev.venue_name)
            for v in self.venues:
                if any(n == incoming or (len(n) >= 4 and n in incoming) for n in self._names(v)):
                    return self._remember_ref(v, ev)

        if ev.venue_lat is not None and ev.venue_lng is not None:
            nearest = min(
                self.venues,
                key=lambda v: haversine_m(v.lat, v.lng, ev.venue_lat, ev.venue_lng),
                default=None,
            )
            if nearest and haversine_m(nearest.lat, nearest.lng, ev.venue_lat, ev.venue_lng) <= VENUE_MATCH_RADIUS_M:
                return self._remember_ref(nearest, ev)

            venue = Venue(
                name=ev.venue_name or "Unknown venue",
                address=ev.venue_address,
                lat=ev.venue_lat,
                lng=ev.venue_lng,
                external_ref=ev.venue_external_ref,
            )
            self.db.add(venue)
            self.db.flush()
            self.venues.append(venue)
            return venue

        return None

    def _remember_ref(self, v: Venue, ev: NormalizedEvent) -> Venue:
        if ev.venue_external_ref and not v.external_ref:
            v.external_ref = ev.venue_external_ref
        return v


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def find_duplicate(db: Session, event: Event) -> Event | None:
    """Return the primary copy of this event from another source, if one exists."""
    if event.venue_id is None:
        return None
    candidates = db.scalars(
        select(Event).where(
            Event.venue_id == event.venue_id,
            Event.source != event.source,
            Event.duplicate_of_id.is_(None),
            Event.start_at >= event.start_at - DUPLICATE_START_TOLERANCE,
            Event.start_at <= event.start_at + DUPLICATE_START_TOLERANCE,
        )
    )
    best, best_score = None, 0.0
    for c in candidates:
        if c.id == event.id:
            continue
        score = _similar(c.title, event.title)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= DUPLICATE_TITLE_SIMILARITY else None


def upsert_events(db: Session, events: list[NormalizedEvent]) -> UpsertResult:
    result = UpsertResult()
    resolver = VenueResolver(db)
    for ev in events:
        venue = resolver.resolve(ev)
        row = db.scalar(
            select(Event).where(Event.source == ev.source, Event.external_id == ev.external_id)
        )
        is_new = row is None
        if is_new:
            row = Event(source=ev.source, external_id=ev.external_id)
            db.add(row)
        row.title = ev.title
        row.category = ev.category
        row.description = ev.description
        row.start_at = ev.start_at
        row.end_at = ev.end_at
        row.url = ev.url
        row.image_url = ev.image_url
        row.expected_attendance = ev.expected_attendance
        row.venue_id = venue.id if venue else None
        db.flush()

        if row.duplicate_of_id is None:
            primary = find_duplicate(db, row)
            if primary is not None:
                row.duplicate_of_id = primary.id
                # Keep the best data on the primary: PredictHQ attendance is
                # more useful than none, Ticketmaster links/images likewise.
                if primary.expected_attendance is None and row.expected_attendance is not None:
                    primary.expected_attendance = row.expected_attendance
                primary.url = primary.url or row.url
                primary.image_url = primary.image_url or row.image_url
                primary.end_at = primary.end_at or row.end_at
                result.duplicates += 1

        if is_new:
            result.created += 1
        else:
            result.updated += 1
    db.commit()
    return result
