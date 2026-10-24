"""Venue matching rules, and repair of links made before Ticketmaster requests sent locale=*.

The coordinates and ids are real Ticketmaster data from the first live sync.
"""

from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text

import app.config
from app.cli import BACKEND_DIR
from app.config import Settings
from app.ingest.base import NormalizedEvent
from app.ingest.store import UNKNOWN_VENUE, upsert_events
from app.models import Event, Venue

SCHLEYER = (48.79370, 9.22654)
SCHRAEGLAGE = (48.77504, 9.17705)   # a club ~70 m from the Marktplatz
LUDWIGSBURG_MHP = (48.89121, 9.18240)  # a different "MHP Arena", 11.6 km north


def tm(ext_id, venue_name, coords, ref, title="Some event"):
    return NormalizedEvent(
        source="ticketmaster", external_id=ext_id, title=title,
        start_at=datetime(2026, 11, 7, 19, tzinfo=timezone.utc),
        venue_name=venue_name, venue_lat=coords[0], venue_lng=coords[1], venue_external_ref=ref,
    )


def venue_of(db, ext_id) -> Venue:
    return db.scalar(select(Event).where(Event.external_id == ext_id)).venue


def seeded(db, name) -> Venue:
    return db.scalar(select(Venue).where(Venue.name == name))


# --- matching rules ----------------------------------------------------------------------

def test_name_match_far_away_is_a_different_venue(db):
    upsert_events(db, [tm("lb", "MHP Arena", LUDWIGSBURG_MHP, "ticketmaster:Z598xZC2Z1F1F", "Basketball")])
    v = venue_of(db, "lb")
    assert v.name == "MHP Arena" and v.id != seeded(db, "MHPArena").id
    assert seeded(db, "MHPArena").external_ref is None


def test_name_match_nearby_links_the_seed_venue(db):
    upsert_events(db, [tm("vfb", "MHP Arena", (48.79164, 9.23130), "ticketmaster:Z698xZC2ZaFwv")])
    assert venue_of(db, "vfb").name == "MHPArena"
    assert seeded(db, "MHPArena").external_ref == "ticketmaster:Z698xZC2ZaFwv"


def test_named_venue_is_never_matched_by_distance_alone(db):
    upsert_events(db, [tm("club", "Schräglage", SCHRAEGLAGE, "ticketmaster:Z698xZC2Za7O4")])
    assert venue_of(db, "club").name == "Schräglage"
    assert seeded(db, "Marktplatz").external_ref is None


def test_nameless_venue_still_matched_by_distance(db):
    upsert_events(db, [tm("x", None, (48.7757, 9.1772), "ticketmaster:Z1")])
    assert venue_of(db, "x").name == "Marktplatz"


# --- repairs on re-sync ----------------------------------------------------------------------

def add_placeholder(db, ref, coords, event_ids) -> int:
    """The state the first live sync left behind: a nameless venue with events on it."""
    v = Venue(name=UNKNOWN_VENUE, lat=coords[0], lng=coords[1], external_ref=ref)
    db.add(v)
    db.flush()
    for ext_id in event_ids:
        db.add(Event(source="ticketmaster", external_id=ext_id, title="Old", venue_id=v.id,
                     start_at=datetime(2026, 11, 7, 19, tzinfo=timezone.utc)))
    db.commit()
    return v.id


def test_placeholder_is_merged_into_the_matching_venue(db):
    ref = "ticketmaster:Z698xZC2ZaAfA"
    placeholder_id = add_placeholder(db, ref, SCHLEYER, ["a", "b"])

    # Next sync delivers the name, but only for event "a"; "b" must move along anyway.
    upsert_events(db, [tm("a", "Hanns-Martin-Schleyer-Halle", SCHLEYER, ref)])
    db.expire_all()
    schleyer = seeded(db, "Hanns-Martin-Schleyer-Halle")
    assert venue_of(db, "a").id == schleyer.id
    assert venue_of(db, "b").id == schleyer.id
    assert schleyer.external_ref == ref
    assert db.get(Venue, placeholder_id) is None


def test_placeholder_without_known_venue_is_renamed(db):
    ref = "ticketmaster:Z698xZC2ZaacR"
    placeholder_id = add_placeholder(db, ref, (48.77615, 9.18422), ["m"])
    upsert_events(db, [tm("m", "StadtPalais- Museum f. Stuttgart", (48.77615, 9.18422), ref)])
    v = venue_of(db, "m")
    assert (v.id, v.name) == (placeholder_id, "StadtPalais- Museum f. Stuttgart")


def test_wrong_distance_link_is_dropped(db):
    ref = "ticketmaster:Z698xZC2Za7O4"
    upsert_events(db, [tm("club", None, SCHRAEGLAGE, ref)])  # old behaviour: nameless → Marktplatz
    assert venue_of(db, "club").name == "Marktplatz"

    upsert_events(db, [tm("club", "Schräglage", SCHRAEGLAGE, ref)])
    assert venue_of(db, "club").name == "Schräglage"
    marktplatz = seeded(db, "Marktplatz")
    assert marktplatz.external_ref is None
    assert venue_of(db, "club").external_ref == ref


# --- migration 0003 ---------------------------------------------------------------------------

def test_migration_moves_only_untouched_seed_coordinates(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    monkeypatch.setattr(app.config, "get_settings", lambda: Settings(database_url=url))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "0002")

    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO venues (name, lat, lng, created_at) VALUES "
                       "('MHPArena', 48.7923, 9.2320, '2026-01-01'),"        # untouched seed
                       "('Im Wizemann', 48.8081, 9.2012, '2026-01-01')"))    # corrected by a manager
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        rows = dict((n, (lat, lng)) for n, lat, lng in c.execute(text("SELECT name, lat, lng FROM venues")))
    assert rows["MHPArena"] == (48.79164, 9.23130)
    assert rows["Im Wizemann"] == (48.8081, 9.2012)

    command.downgrade(cfg, "0002")
    with engine.connect() as c:
        assert c.execute(text("SELECT lat, lng FROM venues WHERE name='MHPArena'")).one() == (48.7923, 9.2320)
    engine.dispose()
