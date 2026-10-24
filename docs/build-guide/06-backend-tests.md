# Chapter 6: Backend tests

Tests prove each part works and **keep proving it** after every later change. In the original build, they caught two real bugs before they reached anyone. Run them all:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```

There are 35 tests in 4 files, taking about 15 seconds.

---

## 6.1 `tests/conftest.py`: the test set-up

pytest loads `conftest.py` automatically. It holds shared *fixtures*: set-up functions that tests request by naming them as parameters.

### Environment first
```python
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["TICKETMASTER_API_KEY"] = ""
os.environ["PREDICTHQ_TOKEN"] = ""
os.environ["ENVIRONMENT"] = "development"
os.environ["ALERT_WEBHOOK_URL"] = ""
os.environ["SENTRY_DSN"] = ""
os.environ["LOG_FORMAT"] = "text"
```
This must come **before** `from app.main import app`, because settings are read at import time. Environment variables beat `.env`, so a developer's real `backend/.env` (with a real API key or webhook) can never leak into tests. Without these lines, running the tests would call the real Ticketmaster API and post real Slack alerts.

### Fixtures
- **`session_factory`**: a fresh **in-memory SQLite** database per test. `StaticPool` makes every connection share the same in-memory database; otherwise each connection would get its own empty one. It creates the tables, seeds the 12 venues, adds `admin@lime-ops.de` and `manager@lime-ops.de`, and closes everything after the test. Each test starts clean, so tests can't affect each other.
- **`db`**: one session from that factory, for tests that work with the database directly.
- **`client`**: FastAPI's `TestClient`, which calls the API in-process without a real server. `app.dependency_overrides[get_db] = ...` makes every endpoint use the test database. This is why `get_db` is a dependency rather than a global.
- **`manager_headers`** and **`admin_headers`**: log in through the real login endpoint and return `{"Authorization": "Bearer …"}`.

> Test emails use `@lime-ops.de`, not `@lime.test`. The `email-validator` library rejects reserved domains like `.test`, which broke the first test run.

---

## 6.2 `tests/fixtures/ticketmaster_events.json`

A hand-made Ticketmaster response with three events:
1. A complete VfB match at "MHPArena Stuttgart", with three images of different sizes.
2. A concert with **only a date** (time TBA) at an unknown venue, "Kulturzentrum Neu".
3. A broken event with no dates.

**Why a fixture file?** Tests must not call the real API: it's slow, needs a key, its data changes every day and it has rate limits. A recorded response makes tests fast and repeatable. Each event is there to test one specific path through `normalize`.

---

## 6.3 `tests/test_ingest.py` (8 tests)

| Test | Proves |
|---|---|
| `test_ticketmaster_normalize_full_event` | Every field is mapped: category `sport`, exact UTC start, **widest** 16:9 image, venue ref, coordinates parsed from strings, address joined. |
| `..._date_only_assumes_evening_local_time` | A TBA time becomes 19:00 **Stuttgart** time, which is 18:00 UTC in November. |
| `..._skips_event_without_start` | A broken event returns `None` instead of crashing. |
| `test_ticketmaster_fetch_pages_and_windows` | Uses `httpx.MockTransport` to fake the API. A 30-day range makes **3** requests (14 + 14 + 2 days), sends the right `latlong` and key, and removes repeated events. |
| `test_predicthq_normalize` | Category mapping, attendance, and **[lng, lat]** coordinate order. |
| `test_upsert_matches_seed_venue_and_creates_unknown` | "MHPArena Stuttgart" matches the seeded "MHPArena" and remembers the venue ref. An unknown venue is created once. A second sync **updates**: counts go from (2 created, 0 updated) to (0, 2), and no venue is duplicated. |
| `test_cross_source_duplicate_links_and_copies_attendance` | The same match from PredictHQ is linked as a duplicate, and its attendance is copied to the Ticketmaster primary. |
| `test_runner_records_success_failure_and_skips_disabled` | With three fake connectors (good, failing, disabled): good → `success`, failing → `failed` without stopping the others, disabled → skipped. The API key is **scrubbed** from the stored error. |

`FakeConnector` is a tiny `Connector` that returns given events or raises a given error. Tests in other files reuse it.

---

## 6.4 `tests/test_deployment.py` (5 tests)

These test the pure recommendation logic with in-memory objects; no database is involved.

| Test | Proves |
|---|---|
| `test_attendance_precedence` | Capacity × fill factor, then the API value wins over that, then the manual value wins over everything; the default applies with no venue. |
| `test_recommendation_scooters_priority_and_windows` | 3,500 × 0.8 = 2,800 visitors → 14 scooters, `medium`, and the exact arrival and departure windows. |
| `test_recommendation_is_capped_and_missing_end_defaults_to_three_hours` | 100,000 visitors → capped at 150; a missing end means departure starts at start + 3 h. |
| `test_multiday_event_spreads_api_attendance_and_uses_daily_hours` | 30,000 over 3 days → 10,000 a day; a middle day opens 11:00 and closes 23:00 local (09:00 and 21:00 UTC in summer time). |
| `test_hotspots_group_nearby_venues_and_use_peak_overlap` | MHPArena and Porsche-Arena merge into one hotspot and Liederhalle stays separate. **The overlap case:** A overlaps B, B overlaps C, A and C don't → peak = 300, not 330. This test caught the first, wrong overlap algorithm. |

---

## 6.5 `tests/test_api.py` (12 tests)

These run through the real HTTP layer.

| Test | Proves |
|---|---|
| `test_requires_auth` | No token or a garbage token → 401. |
| `test_login_rejects_wrong_password` | → 401. |
| `test_me_and_role_checks` | A manager gets 403 on the users and ingest endpoints; an admin gets 200. |
| `test_admin_creates_user_who_can_log_in` | Email case is ignored ("New@…" logs in as "new@…"). |
| `test_admin_cannot_demote_self` | → 400. |
| `test_day_view_includes_recommendations_and_hotspots` | The full day response: venue, `capacity` source, `high` priority, hotspot capped at 150. |
| `test_day_boundaries_use_stuttgart_local_time` | 23:30 Stuttgart time on the 7th is 22:30 UTC, and it belongs to the 7th, not the 8th. **The most important timezone test.** |
| `test_duplicates_are_hidden` | Only the primary is listed. |
| `test_calendar_summary_and_range_limits` | A 3-day expo appears on each of its days with `high` priority; over 100 days or an unknown category → 422. |
| `test_manual_event_crud` | Create with a new venue, edit, end-before-start rejected, **timezone-less time rejected**, delete, then 404. |
| `test_imported_events_only_accept_attendance_override` | Editing or deleting an imported event → 400; an override of 12,000 → 60 scooters, source `manual`. |
| `test_ingest_run_without_sources_is_rejected` | → 400; both sources show as not configured. |

---

## 6.6 `tests/test_production.py` (10 tests)

| Test | Proves |
|---|---|
| `test_production_refuses_default_secret_and_sqlite` | Production with the default secret or SQLite raises; a good config passes; development tolerates both. |
| `test_json_log_format` | Each line is valid JSON with the right fields. |
| `test_health_checks_database` | `{"status": "ok", "database": "ok"}`. |
| `test_ingest_health` | 503 with no source, then 503 when never synced, 503 when 40 h old, 503 when only a recent *failed* run exists, and 200 after a recent success. |
| `test_alerts_for_failed_and_empty_syncs` | Replaces `httpx.post` with a fake that records messages: exactly 2 alerts, one for 0 events and one for a failure, and none for a success. |
| `test_broken_webhook_does_not_raise` | A webhook network error is swallowed. |
| `test_run_in_another_process_blocks_new_runs` | A fresh `running` row (as another process would leave it) → `IngestAlreadyRunning`, and the API returns 409. |
| `test_stale_running_row_is_ignored` | A 3-hour-old `running` row doesn't block. **This test caught the `db.merge` bug** described in chapter 3. |
| `test_purge_old_events_keeps_recent_and_removes_dependent_duplicates` | Removes 2 old events plus 1 duplicate pointing at an old one, and keeps the recent event. |
| `test_audit_fields` | The manager creates an event, the admin overrides visitors, and `created_by` and `updated_by` show the right people, including in the day view. |

### The `monkeypatch` fixture
`monkeypatch.setattr(module, "name", replacement)` temporarily swaps something for one test and restores it afterwards. It's used to give `alerts` a webhook URL, fake `httpx.post`, and make `runner.all_connectors` return a fake enabled connector. This is how you test code that talks to the outside world without actually talking to it.

## Checkpoint

`pytest -q` shows `35 passed`. Then **break something on purpose**: change `ARRIVAL_LEAD` to 60 minutes and run again. A test should fail. Change it back. A test suite you've never seen fail is a suite you can't trust.

Next: [Chapter 7, Frontend](07-frontend.md).
