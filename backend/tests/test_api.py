from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Event, Venue


def _venue_id(session_factory, name):
    with session_factory() as db:
        return db.scalar(select(Venue.id).where(Venue.name == name))


def _add_imported_event(session_factory, **kw):
    with session_factory() as db:
        e = Event(source="ticketmaster", external_id=kw.pop("external_id", "tm1"), **kw)
        db.add(e)
        db.commit()
        return e.id


def test_requires_auth(client):
    assert client.get("/api/events/day/2026-11-07").status_code == 401
    assert client.get("/api/venues", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_rejects_wrong_password(client):
    resp = client.post("/api/auth/login", json={"email": "manager@lime-ops.de", "password": "nope-nope"})
    assert resp.status_code == 401


def test_me_and_role_checks(client, manager_headers, admin_headers):
    assert client.get("/api/auth/me", headers=manager_headers).json()["role"] == "manager"
    assert client.get("/api/users", headers=manager_headers).status_code == 403
    assert client.get("/api/ingest/runs", headers=manager_headers).status_code == 403
    assert client.get("/api/users", headers=admin_headers).status_code == 200


def test_admin_creates_user_who_can_log_in(client, admin_headers):
    resp = client.post("/api/users", headers=admin_headers,
                       json={"email": "New@Lime-Ops.de", "password": "password123", "role": "manager"})
    assert resp.status_code == 201
    login = client.post("/api/auth/login", json={"email": "new@lime-ops.de", "password": "password123"})
    assert login.status_code == 200


def test_admin_cannot_demote_self(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    resp = client.patch(f"/api/users/{me['id']}", headers=admin_headers, json={"role": "manager"})
    assert resp.status_code == 400


def test_day_view_includes_recommendations_and_hotspots(client, manager_headers, session_factory):
    stadium = _venue_id(session_factory, "MHPArena")
    _add_imported_event(session_factory, title="VfB - Bayern", category="sport", venue_id=stadium,
                        start_at=datetime(2026, 11, 7, 14, 30, tzinfo=timezone.utc),
                        end_at=datetime(2026, 11, 7, 16, 30, tzinfo=timezone.utc))
    resp = client.get("/api/events/day/2026-11-07", headers=manager_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["event_count"] == 1
    ev = body["events"][0]
    assert ev["venue"]["name"] == "MHPArena"
    assert ev["recommendation"]["attendance_source"] == "capacity"
    assert ev["recommendation"]["priority"] == "high"
    assert body["hotspots"][0]["name"] == "MHPArena"
    assert body["hotspots"][0]["extra_scooters"] == 150  # capped


def test_day_boundaries_use_stuttgart_local_time(client, manager_headers, session_factory):
    # 23:30 local on 7 Nov (CET) is 22:30 UTC: belongs to the 7th, not the 8th.
    _add_imported_event(session_factory, title="Late show", category="concert",
                        start_at=datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc),
                        end_at=datetime(2026, 11, 7, 22, 59, tzinfo=timezone.utc))
    day7 = client.get("/api/events/day/2026-11-07", headers=manager_headers).json()
    day8 = client.get("/api/events/day/2026-11-08", headers=manager_headers).json()
    assert [e["title"] for e in day7["events"]] == ["Late show"]
    assert day8["events"] == []


def test_duplicates_are_hidden(client, manager_headers, session_factory):
    primary = _add_imported_event(session_factory, title="A", start_at=datetime(2026, 11, 7, 18, tzinfo=timezone.utc))
    _add_imported_event(session_factory, external_id="tm2", title="A copy", duplicate_of_id=primary,
                        start_at=datetime(2026, 11, 7, 18, tzinfo=timezone.utc))
    titles = [e["title"] for e in client.get("/api/events/day/2026-11-07", headers=manager_headers).json()["events"]]
    assert titles == ["A"]


def test_calendar_summary_and_range_limits(client, manager_headers, session_factory):
    _add_imported_event(session_factory, title="Expo", category="expo",
                        venue_id=_venue_id(session_factory, "Messe Stuttgart"),
                        start_at=datetime(2026, 11, 10, 8, tzinfo=timezone.utc),
                        end_at=datetime(2026, 11, 12, 16, tzinfo=timezone.utc))
    resp = client.get("/api/events/summary?start=2026-11-01&end=2026-12-01", headers=manager_headers)
    assert resp.status_code == 200
    days = {d["date"]: d for d in resp.json()}
    assert sorted(days) == ["2026-11-10", "2026-11-11", "2026-11-12"]
    assert days["2026-11-11"]["event_count"] == 1
    assert days["2026-11-11"]["priority"] == "high"  # 40000 * 0.5 per day

    assert client.get("/api/events?start=2026-11-01&end=2027-06-01", headers=manager_headers).status_code == 422
    assert client.get("/api/events?start=2026-11-01&end=2026-12-01&category=nope",
                      headers=manager_headers).status_code == 422


def test_manual_event_crud(client, manager_headers):
    resp = client.post("/api/events", headers=manager_headers, json={
        "title": "Cannstatter Volksfest",
        "category": "festival",
        "start_at": "2026-09-25T11:00:00+02:00",
        "end_at": "2026-09-25T23:00:00+02:00",
        "new_venue": {"name": "Wasen Nord", "lat": 48.796, "lng": 9.219, "capacity": 50000},
    })
    assert resp.status_code == 201, resp.text
    ev = resp.json()
    assert ev["is_manual"] and ev["venue"]["name"] == "Wasen Nord"

    resp = client.patch(f"/api/events/{ev['id']}", headers=manager_headers, json={"title": "Volksfest day 1"})
    assert resp.json()["title"] == "Volksfest day 1"

    bad = client.patch(f"/api/events/{ev['id']}", headers=manager_headers,
                       json={"end_at": "2026-09-25T08:00:00+02:00"})
    assert bad.status_code == 422

    naive = client.post("/api/events", headers=manager_headers,
                        json={"title": "x", "start_at": "2026-09-25T11:00:00"})
    assert naive.status_code == 422

    assert client.delete(f"/api/events/{ev['id']}", headers=manager_headers).status_code == 204
    assert client.get(f"/api/events/{ev['id']}", headers=manager_headers).status_code == 404


def test_imported_events_only_accept_attendance_override(client, manager_headers, session_factory):
    eid = _add_imported_event(session_factory, title="Concert", category="concert",
                              start_at=datetime(2026, 11, 7, 18, tzinfo=timezone.utc))
    assert client.patch(f"/api/events/{eid}", headers=manager_headers, json={"title": "x"}).status_code == 400
    assert client.delete(f"/api/events/{eid}", headers=manager_headers).status_code == 400

    resp = client.put(f"/api/events/{eid}/attendance", headers=manager_headers, json={"attendance_override": 12000})
    assert resp.json()["attendance_override"] == 12000
    day = client.get("/api/events/day/2026-11-07", headers=manager_headers).json()
    rec = day["events"][0]["recommendation"]
    assert (rec["attendance"], rec["attendance_source"], rec["extra_scooters"]) == (12000, "manual", 60)


def test_ingest_run_without_sources_is_rejected(client, admin_headers):
    resp = client.post("/api/ingest/run", headers=admin_headers)
    assert resp.status_code == 400
    sources = client.get("/api/ingest/sources", headers=admin_headers).json()
    assert {s["name"]: s["enabled"] for s in sources} == {"ticketmaster": False, "predicthq": False}
