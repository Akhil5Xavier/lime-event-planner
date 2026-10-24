from datetime import date, datetime, timedelta, timezone

from app.config import Settings
from app.models import Event, Venue
from app.services.deployment import build_hotspots, estimate_attendance, recommend

SETTINGS = Settings(scooter_share=0.005, max_scooters_per_spot=150, hotspot_radius_m=500)
STADIUM = Venue(id=1, name="MHPArena", lat=48.7923, lng=9.2320, capacity=60000)
ARENA = Venue(id=2, name="Porsche-Arena", lat=48.7884, lng=9.2266, capacity=7500)
LIEDERHALLE = Venue(id=3, name="Liederhalle", lat=48.7781, lng=9.1706, capacity=3500)


def make_event(id, venue, start, hours=2.0, category="concert", **kw):
    return Event(id=id, title=f"E{id}", category=category, venue=venue, start_at=start,
                 end_at=start + timedelta(hours=hours) if hours else None, **kw)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_attendance_precedence():
    e = make_event(1, STADIUM, utc(2026, 11, 7, 14), category="sport")
    assert estimate_attendance(e) == (54000, "capacity")  # 60000 * 0.9
    e.expected_attendance = 58000
    assert estimate_attendance(e) == (58000, "api")
    e.attendance_override = 40000
    assert estimate_attendance(e) == (40000, "manual")
    no_venue = make_event(2, None, utc(2026, 11, 7, 14), category="theatre")
    assert estimate_attendance(no_venue) == (500, "default")


def test_recommendation_scooters_priority_and_windows():
    start = utc(2026, 11, 7, 14, 30)
    rec = recommend(make_event(1, LIEDERHALLE, start, hours=2), date(2026, 11, 7), SETTINGS)
    assert rec.attendance == 2800  # 3500 * 0.8
    assert rec.extra_scooters == 14  # ceil(2800 * 0.005)
    assert rec.priority == "medium"
    arrival, departure = rec.windows
    assert (arrival.start, arrival.end) == (start - timedelta(minutes=90), start)
    assert (departure.start, departure.end) == (start + timedelta(hours=2), start + timedelta(hours=3))


def test_recommendation_is_capped_and_missing_end_defaults_to_three_hours():
    start = utc(2026, 11, 7, 14, 30)
    e = make_event(1, STADIUM, start, hours=None, category="sport", attendance_override=100_000)
    rec = recommend(e, date(2026, 11, 7), SETTINGS)
    assert rec.extra_scooters == 150
    assert rec.priority == "high"
    assert rec.windows[1].start == start + timedelta(hours=3)


def test_multiday_event_spreads_api_attendance_and_uses_daily_hours():
    # Volksfest-style event: 3 days, 30k total predicted visitors.
    e = make_event(1, STADIUM, utc(2026, 9, 25, 9), hours=24 * 2 + 12, category="festival",
                   expected_attendance=30000)
    rec = recommend(e, date(2026, 9, 26), SETTINGS)
    assert rec.attendance == 10000
    # Middle day: open 11:00 local (09:00 UTC in CEST), close 23:00 local.
    assert rec.windows[0].end == utc(2026, 9, 26, 9)
    assert rec.windows[1].start == utc(2026, 9, 26, 21)


def test_hotspots_group_nearby_venues_and_use_peak_overlap():
    day = date(2026, 11, 7)
    # Spans include the 90 min arrival and 60 min departure windows (UTC):
    football = make_event(1, STADIUM, utc(2026, 11, 7, 14, 30), category="sport")  # 13:00-17:30, 270
    arena_mid = make_event(2, ARENA, utc(2026, 11, 7, 16), hours=1)  # 14:30-18:00, 30
    arena_evening = make_event(3, ARENA, utc(2026, 11, 7, 19))  # 17:30-22:00, 30
    city = make_event(4, LIEDERHALLE, utc(2026, 11, 7, 18))  # 14, other side of town
    events = [football, arena_mid, arena_evening, city]
    settings = Settings(scooter_share=0.005, max_scooters_per_spot=500, hotspot_radius_m=600)
    recs = {e.id: recommend(e, day, settings) for e in events}
    assert recs[1].extra_scooters == 270

    hotspots = build_hotspots(events, recs, settings)
    assert len(hotspots) == 2
    neckarpark, centre = hotspots
    assert neckarpark.name == "MHPArena area"
    assert sorted(neckarpark.event_ids) == [1, 2, 3]
    # arena_mid overlaps both others, but football and arena_evening never overlap each
    # other (back-to-back at 17:30), so the peak is 270 + 30, not 270 + 30 + 30.
    assert neckarpark.extra_scooters == 300
    assert neckarpark.priority == "high"
    assert centre.name == "Liederhalle"
    assert centre.extra_scooters == 14
