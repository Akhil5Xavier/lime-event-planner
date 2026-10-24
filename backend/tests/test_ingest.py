import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import Settings
from app.ingest import runner
from app.ingest.base import Connector, NormalizedEvent
from app.ingest.predicthq import normalize as phq_normalize
from app.ingest.store import upsert_events
from app.ingest.ticketmaster import TicketmasterConnector, normalize
from app.models import Event, IngestRun, Venue

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ticketmaster_events.json").read_text("utf-8"))
TM_EVENTS = FIXTURE["_embedded"]["events"]


def test_ticketmaster_normalize_full_event():
    ev = normalize(TM_EVENTS[0])
    assert ev.source == "ticketmaster"
    assert ev.external_id == "Z698xZb_Z17kv4a"
    assert ev.category == "sport"
    assert ev.start_at == datetime(2026, 11, 7, 14, 30, tzinfo=timezone.utc)
    assert ev.image_url == "https://img.example/vfb_16_9_large.jpg"
    assert ev.venue_external_ref == "ticketmaster:Z598xZb_ZeAke"
    assert (ev.venue_lat, ev.venue_lng) == (48.79227, 9.23202)
    assert ev.venue_address == "Mercedesstraße 87, 70372, Stuttgart"


def test_ticketmaster_normalize_date_only_assumes_evening_local_time():
    ev = normalize(TM_EVENTS[1])
    assert ev.category == "concert"
    # 19:00 Berlin (CET in November) == 18:00 UTC
    assert ev.start_at.astimezone(timezone.utc) == datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc)


def test_ticketmaster_normalize_skips_event_without_start():
    assert normalize(TM_EVENTS[2]) is None


def test_ticketmaster_fetch_pages_and_windows():
    calls = []

    def handler(request: httpx.Request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=FIXTURE)

    connector = TicketmasterConnector(
        Settings(ticketmaster_api_key="KEY"), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    events = connector.fetch(start, start + timedelta(days=30))
    # 30 days split into 14-day windows -> 3 requests; events deduped by id.
    assert len(calls) == 3
    assert calls[0]["latlong"] == "48.7758,9.1829"
    assert calls[0]["apikey"] == "KEY"
    assert {e.external_id for e in events} == {"Z698xZb_Z17kv4a", "Z698xZb_Z17kv4b"}


def test_predicthq_normalize():
    ev = phq_normalize({
        "id": "phq1",
        "title": "VfB Stuttgart vs FC Bayern",
        "category": "sports",
        "start": "2026-11-07T14:30:00Z",
        "end": "2026-11-07T16:30:00Z",
        "phq_attendance": 58000,
        "geo": {"geometry": {"type": "Point", "coordinates": [9.2320, 48.7923]}},
        "entities": [{"type": "venue", "name": "MHPArena", "entity_id": "v1", "formatted_address": "x"}],
    })
    assert ev.category == "sport"
    assert ev.expected_attendance == 58000
    assert (ev.venue_lat, ev.venue_lng) == (48.7923, 9.2320)


def test_upsert_matches_seed_venue_and_creates_unknown(db):
    events = [normalize(raw) for raw in TM_EVENTS[:2]]
    res = upsert_events(db, events)
    assert (res.created, res.updated) == (2, 0)

    vfb = db.scalar(select(Event).where(Event.external_id == "Z698xZb_Z17kv4a"))
    assert vfb.venue.name == "MHPArena"
    assert vfb.venue.external_ref == "ticketmaster:Z598xZb_ZeAke"

    rock = db.scalar(select(Event).where(Event.external_id == "Z698xZb_Z17kv4b"))
    assert rock.venue.name == "Kulturzentrum Neu"
    assert rock.venue.capacity is None

    # Second run updates in place.
    events[0].title = "VfB Stuttgart - FC Bayern (sold out)"
    res = upsert_events(db, events)
    assert (res.created, res.updated) == (0, 2)
    assert db.scalar(select(Event).where(Event.external_id == "Z698xZb_Z17kv4a")).title.endswith("(sold out)")
    assert db.query(Venue).filter(Venue.name == "Kulturzentrum Neu").count() == 1


def test_cross_source_duplicate_links_and_copies_attendance(db):
    upsert_events(db, [normalize(TM_EVENTS[0])])
    phq = NormalizedEvent(
        source="predicthq",
        external_id="phq1",
        title="VfB Stuttgart vs. FC Bayern München",
        start_at=datetime(2026, 11, 7, 14, 30, tzinfo=timezone.utc),
        category="sport",
        expected_attendance=58000,
        venue_name="MHPArena",
        venue_lat=48.7923,
        venue_lng=9.2320,
    )
    res = upsert_events(db, [phq])
    assert res.duplicates == 1

    tm = db.scalar(select(Event).where(Event.source == "ticketmaster"))
    dup = db.scalar(select(Event).where(Event.source == "predicthq"))
    assert dup.duplicate_of_id == tm.id
    assert tm.expected_attendance == 58000


class FakeConnector(Connector):
    def __init__(self, name, events=None, error=None, enabled=True):
        self.name, self._events, self._error, self._enabled = name, events or [], error, enabled

    def is_enabled(self):
        return self._enabled

    def fetch(self, start, end):
        if self._error:
            raise self._error
        return self._events


def test_runner_records_success_failure_and_skips_disabled(session_factory, monkeypatch):
    monkeypatch.setattr(runner, "get_settings", lambda: Settings(ticketmaster_api_key="SECRET123"))
    runs = runner.run_ingestion(
        trigger="manual",
        connectors=[
            FakeConnector("good", [normalize(TM_EVENTS[0])]),
            FakeConnector("bad", error=RuntimeError("GET https://x/?apikey=SECRET123 failed")),
            FakeConnector("off", enabled=False),
        ],
        session_factory=session_factory,
    )
    assert [(r.source, r.status) for r in runs] == [("good", "success"), ("bad", "failed")]
    with session_factory() as db:
        stored = {r.source: r for r in db.scalars(select(IngestRun))}
    assert stored["good"].created == 1
    assert "SECRET123" not in stored["bad"].error
    assert "***" in stored["bad"].error
