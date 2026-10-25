import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app import alerts
from app.config import Settings
from app.ingest import runner
from app.models import Event, IngestRun
from app.observability import JsonFormatter
from app.services.cleanup import purge_old_events
from tests.test_ingest import TM_EVENTS, FakeConnector, normalize

GOOD_SECRET = "x" * 40
PG_URL = "postgresql+psycopg://lime:pw@db:5432/lime"


# --- production config -------------------------------------------------------

def test_production_refuses_default_secret_and_sqlite():
    with pytest.raises(RuntimeError, match="JWT_SECRET.*SQLite"):
        Settings(environment="production").check_production()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret="short", database_url=PG_URL).check_production()
    Settings(environment="production", jwt_secret=GOOD_SECRET, database_url=PG_URL).check_production()
    # Development tolerates both.
    Settings(environment="development").check_production()


def test_json_log_format():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "synced %s events", (12,), None)
    entry = json.loads(JsonFormatter().format(record))
    assert entry["level"] == "INFO" and entry["message"] == "synced 12 events" and entry["logger"] == "app.test"


# --- health endpoints --------------------------------------------------------

def test_health_checks_database(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def _add_run(session_factory, status, finished_ago=None, started_ago=timedelta(0)):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(IngestRun(source="ticketmaster", status=status, started_at=now - started_ago,
                         finished_at=now - finished_ago if finished_ago is not None else None))
        db.commit()


def test_ingest_health(client, session_factory, monkeypatch):
    assert client.get("/api/health/ingest").status_code == 503  # no source configured

    monkeypatch.setattr(runner, "all_connectors", lambda: [FakeConnector("ticketmaster")])
    resp = client.get("/api/health/ingest")
    assert resp.status_code == 503 and resp.json()["status"] == "stale"  # never synced

    _add_run(session_factory, "success", finished_ago=timedelta(hours=40))
    assert client.get("/api/health/ingest").status_code == 503  # too old

    _add_run(session_factory, "failed", finished_ago=timedelta(hours=1))
    assert client.get("/api/health/ingest").status_code == 503  # failures don't count

    _add_run(session_factory, "success", finished_ago=timedelta(hours=2))
    resp = client.get("/api/health/ingest")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"


# --- sync alerts and locking ---------------------------------------------------

def test_alerts_for_failed_and_empty_syncs(session_factory, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "get_settings", lambda: Settings(alert_webhook_url="https://hooks.example/x"))
    monkeypatch.setattr(alerts.httpx, "post",
                        lambda url, json, timeout: sent.append(json) or httpx.Response(200, request=httpx.Request("POST", url)))
    runner.run_ingestion(
        connectors=[
            FakeConnector("good", [normalize(TM_EVENTS[0])]),
            FakeConnector("empty", []),
            FakeConnector("bad", error=RuntimeError("boom")),
        ],
        session_factory=session_factory,
    )
    texts = [m["text"] for m in sent]
    assert len(texts) == 2
    assert "*empty*" in texts[0] and "0 events" in texts[0]
    assert "*bad*" in texts[1] and "boom" in texts[1]


def test_broken_webhook_does_not_raise(monkeypatch):
    monkeypatch.setattr(alerts, "get_settings", lambda: Settings(alert_webhook_url="https://hooks.example/x"))

    def fail(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(alerts.httpx, "post", fail)
    alerts.send_alert("hello")  # logged, not raised


def test_run_in_another_process_blocks_new_runs(client, admin_headers, session_factory):
    _add_run(session_factory, "running", started_ago=timedelta(minutes=5))
    with pytest.raises(runner.IngestAlreadyRunning):
        runner.run_ingestion(connectors=[FakeConnector("good")], session_factory=session_factory)
    assert client.post("/api/ingest/run", headers=admin_headers).status_code == 409


def test_stale_running_row_is_ignored(session_factory):
    _add_run(session_factory, "running", started_ago=timedelta(hours=3))
    runs = runner.run_ingestion(connectors=[FakeConnector("good")], session_factory=session_factory)
    assert [r.status for r in runs] == ["success"]


# --- retention -------------------------------------------------------------------

def test_purge_old_events_keeps_recent_and_removes_dependent_duplicates(db):
    now = datetime.now(timezone.utc)
    old = Event(source="ticketmaster", external_id="old", title="Old",
                start_at=now - timedelta(days=400), end_at=now - timedelta(days=400) + timedelta(hours=2))
    old_no_end = Event(source="ticketmaster", external_id="old2", title="Old 2", start_at=now - timedelta(days=500))
    recent = Event(source="ticketmaster", external_id="new", title="Recent", start_at=now - timedelta(days=10))
    db.add_all([old, old_no_end, recent])
    db.flush()
    dup = Event(source="predicthq", external_id="dup", title="Old (copy)", duplicate_of_id=old.id,
                start_at=now - timedelta(days=10))  # odd but possible: dup's own dates are recent
    db.add(dup)
    db.commit()

    assert purge_old_events(db, retention_days=365) == 3
    assert [e.title for e in db.scalars(select(Event))] == ["Recent"]


# --- audit trail ------------------------------------------------------------------

def test_audit_fields(client, manager_headers, admin_headers):
    ev = client.post("/api/events", headers=manager_headers, json={
        "title": "Weindorf", "category": "festival", "start_at": "2026-11-07T11:00:00+01:00",
    }).json()
    assert ev["created_by"]["email"] == "manager@lime-ops.de"
    assert ev["updated_by"]["email"] == "manager@lime-ops.de"

    ev = client.put(f"/api/events/{ev['id']}/attendance", headers=admin_headers,
                    json={"attendance_override": 5000}).json()
    assert ev["created_by"]["email"] == "manager@lime-ops.de"
    assert ev["updated_by"]["email"] == "admin@lime-ops.de"

    day = client.get("/api/events/day/2026-11-07", headers=manager_headers).json()
    assert day["events"][0]["updated_by"]["email"] == "admin@lime-ops.de"


# --- one-command start: first admin and catch-up sync -------------------------------------

def test_bootstrap_admin_only_when_no_users(session_factory, monkeypatch):
    import app.config
    from app.cli import bootstrap_admin
    from app.models import User
    from app.security import verify_password

    monkeypatch.setattr(app.config, "get_settings",
                        lambda: Settings(admin_email="Boss@Lime-Ops.de", admin_password="first-pass-123"))
    with session_factory() as db:
        assert bootstrap_admin(db) is None  # conftest already created users
        db.query(User).delete()
        db.commit()
        assert bootstrap_admin(db) == "boss@lime-ops.de"
        user = db.scalar(select(User))
        assert user.role == "admin" and verify_password("first-pass-123", user.password_hash)
        # A second start must not create another admin or touch the password.
        monkeypatch.setattr(app.config, "get_settings",
                            lambda: Settings(admin_email="boss@lime-ops.de", admin_password="changed-pass-456"))
        assert bootstrap_admin(db) is None
        assert verify_password("first-pass-123", db.scalar(select(User)).password_hash)


def test_bootstrap_admin_needs_both_settings_and_a_real_password(db, monkeypatch):
    import app.config
    from app.cli import bootstrap_admin
    from app.models import User

    db.query(User).delete()
    db.commit()
    for settings in (Settings(), Settings(admin_email="a@lime-ops.de"),
                     Settings(admin_email="a@lime-ops.de", admin_password="short")):
        monkeypatch.setattr(app.config, "get_settings", lambda s=settings: s)
        assert bootstrap_admin(db) is None
    assert db.query(User).count() == 0


def test_worker_catches_up_when_data_is_stale(session_factory, monkeypatch):
    from app import scheduler

    assert scheduler.needs_catch_up(session_factory) is False  # no source configured
    monkeypatch.setattr(runner, "all_connectors", lambda: [FakeConnector("ticketmaster")])
    assert scheduler.needs_catch_up(session_factory) is True   # never synced
    _add_run(session_factory, "success", finished_ago=timedelta(hours=40))
    assert scheduler.needs_catch_up(session_factory) is True   # too old
    _add_run(session_factory, "success", finished_ago=timedelta(hours=3))
    assert scheduler.needs_catch_up(session_factory) is False
