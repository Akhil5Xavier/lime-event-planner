"""Writes normalized events to the database: venue matching, upsert and cross-source dedupe."""

from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.geo import haversine_m, normalize_name
from app.ingest.base import NormalizedEvent
from app.models import Event, Venue

VENUE_MATCH_RADIUS_M = 150
# A name match further away than this is a different place with the same name
# (e.g. the "MHP Arena" in Ludwigsburg, 11.6 km from Stuttgart's MHPArena).
NAME_MATCH_MAX_DISTANCE_M = 3000
# Name given to venues that arrived without one (before Ticketmaster requests sent
# locale=*). Such rows are repaired as soon as a sync delivers the real name.
UNKNOWN_VENUE = "Unknown venue"
DUPLICATE_START_TOLERANCE = timedelta(hours=1)
DUPLICATE_TITLE_SIMILARITY = 0.6


@dataclass
class UpsertResult:
    created: int = 0
    updated: int = 0
    duplicates: int = 0


class VenueResolver:
    """Maps API venue info to a Venue row, creating one when nothing matches.

    Order:
      1. the venue already linked to this API venue id (external ref);
      2. a venue whose name or alias matches, if it is within NAME_MATCH_MAX_DISTANCE_M;
      3. only for venues that arrive *without a name*: a known venue within 150 m;
      4. otherwise a new venue.
    A named venue is never matched by distance alone: in the city centre a club 100 m from
    the Marktplatz is still a different place with a very different capacity.

    Links made under the old rules are repaired when a sync delivers a name that doesn't fit:
    an "Unknown venue" placeholder is merged into the matching venue (or renamed), and a
    wrong distance-based link is dropped so the event gets its proper venue.

    Loads venues once per run so a run with thousands of events stays cheap.
    """

    def __init__(self, db: Session):
        self.db = db
        self.venues: list[Venue] = list(db.scalars(select(Venue)))

    def _names(self, v: Venue) -> list[str]:
        names = [v.name] + [a for a in (v.aliases or "").split("|") if a]
        return [n for n in map(normalize_name, names) if n]

    def _name_matches(self, v: Venue, venue_name: str) -> bool:
        incoming = normalize_name(venue_name)
        return any(n == incoming or (len(n) >= 4 and n in incoming) for n in self._names(v))

    @staticmethod
    def _near(v: Venue, ev: NormalizedEvent, radius_m: float) -> bool:
        if ev.venue_lat is None or ev.venue_lng is None:
            return True  # nothing to compare; trust the name
        return haversine_m(v.lat, v.lng, ev.venue_lat, ev.venue_lng) <= radius_m

    def _by_name(self, ev: NormalizedEvent, exclude: Venue | None = None) -> Venue | None:
        for v in self.venues:
            if v is exclude or v.name == UNKNOWN_VENUE:
                continue
            if self._name_matches(v, ev.venue_name) and self._near(v, ev, NAME_MATCH_MAX_DISTANCE_M):
                return v
        return None

    def resolve(self, ev: NormalizedEvent) -> Venue | None:
        if ev.venue_external_ref:
            linked = next((v for v in self.venues if v.external_ref == ev.venue_external_ref), None)
            if linked is not None:
                if not ev.venue_name or self._name_matches(linked, ev.venue_name):
                    return linked
                if linked.name == UNKNOWN_VENUE:
                    return self._repair_placeholder(linked, ev)
                # Linked under the old distance rule to a different place: drop the link.
                linked.external_ref = None

        if ev.venue_name:
            match = self._by_name(ev)
            if match is not None:
                return self._remember_ref(match, ev)
        elif ev.venue_lat is not None and ev.venue_lng is not None:
            nearest = min(
                self.venues,
                key=lambda v: haversine_m(v.lat, v.lng, ev.venue_lat, ev.venue_lng),
                default=None,
            )
            if nearest and self._near(nearest, ev, VENUE_MATCH_RADIUS_M):
                return self._remember_ref(nearest, ev)

        if ev.venue_lat is None or ev.venue_lng is None:
            return None
        venue = Venue(
            name=ev.venue_name or UNKNOWN_VENUE,
            address=ev.venue_address,
            lat=ev.venue_lat,
            lng=ev.venue_lng,
            external_ref=ev.venue_external_ref,
        )
        self.db.add(venue)
        self.db.flush()
        self.venues.append(venue)
        return venue

    def _repair_placeholder(self, placeholder: Venue, ev: NormalizedEvent) -> Venue:
        """The API now tells us the real name of a venue stored as "Unknown venue"."""
        target = self._by_name(ev, exclude=placeholder)
        if target is None:
            placeholder.name = ev.venue_name
            placeholder.address = ev.venue_address or placeholder.address
            return placeholder
        # Same place as a known venue: move its events over and drop the placeholder.
        self.db.flush()
        self.db.execute(
            update(Event).where(Event.venue_id == placeholder.id).values(venue_id=target.id),
            execution_options={"synchronize_session": "fetch"},
        )
        self.db.execute(delete(Venue).where(Venue.id == placeholder.id))
        self.db.expunge(placeholder)
        self.venues.remove(placeholder)
        return self._remember_ref(target, ev)

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
