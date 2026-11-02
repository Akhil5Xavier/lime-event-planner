# Chapter 6: Testing

Tests prove each part works and **keep proving it** after every later change. In this project they caught real bugs before anyone saw them: a wrong overlap algorithm, a stale "running" status after a refactor, a wrong number format check, and more (chapter 9).

This chapter covers all of it:
1. **Automated backend tests:** 85 tests in 7 files, run with pytest in about 10 seconds.
2. **Frontend checks:** the TypeScript typecheck and production build.
3. **Manual and live checks:** what can't be automated (real Ticketmaster, the real AI model, the browser, Docker) and how it was checked.
4. **CI:** what runs automatically on every push.

---

## 6.1 Running the tests

```powershell
cd D:\Projects\Lime\backend
.venv\Scripts\python.exe -m pytest -q
```
Expected: `85 passed`. Useful variants:

| Command | What for |
|---|---|
| `pytest -q tests/test_assistant.py` | One file |
| `pytest -q -k venue` | Only tests whose name contains "venue" |
| `pytest -q -x` | Stop at the first failure |
| `pytest -q --durations=5` | Show the 5 slowest tests (this found the bcrypt slowdown, chapter 9 bug 25) |
| `pytest -q -p no:warnings` | Hide library deprecation warnings |

### The tools
| Tool | Version | Used for |
|---|---|---|
| **pytest** | 9.1 | Test runner: finds `test_*.py` files and `test_*` functions, runs them, reports failures with a diff. |
| **FastAPI `TestClient`** | (with FastAPI) | Calls the real API in-process without starting a server: the real routing, validation, auth and JSON. |
| **`httpx.MockTransport`** | (with httpx) | A fake HTTP server for code that calls Ticketmaster or the AI provider. Returns prepared responses and records the requests. |
| **SQLite in memory** | (with Python) | A fresh, empty database for every test, in milliseconds. |
| **`monkeypatch`** | (pytest built-in) | Temporarily replaces a function or setting for one test, then restores it. |
| **`pytest.mark.parametrize`** | (pytest built-in) | Runs one test with many inputs (for example 8 kinds of bad tool input). |

### What is tested, by file

| File | Tests | Area |
|---|---|---|
| `test_ingest.py` | 8 | Ticketmaster and PredictHQ parsing, paging, upsert, duplicates, sync runner |
| `test_venue_matching.py` | 8 | Venue matching rules, repair of old links, migration 0003 |
| `test_deployment.py` | 5 | Scooter recommendation and hotspots (pure logic) |
| `test_api.py` | 12 | REST API: auth, roles, day view, timezones, calendar, event CRUD |
| `test_production.py` | 13 | Production safety, health checks, alerts, locks, retention, audit, first admin, catch-up sync |
| `test_assistant.py` | 34 | AI assistant: tools, prompt, tool loop with a fake provider, errors, `/api/chat` |
| `test_cli.py` | 5 | The `set-password` command |
| **Total** | **85** | |

---

## 6.2 The shared set-up: `tests/conftest.py`

pytest loads `conftest.py` automatically. It holds shared **fixtures**, set-up functions that a test requests by naming them as parameters (`def test_x(client, admin_headers): ...`).

### 1. Environment first
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
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = "https://api.groq.com/openai/v1"
```
These lines come **before** `from app.main import app`, because settings are read at import time. Environment variables beat `backend/.env`, so your real Ticketmaster key, Groq key or Slack webhook can **never** be used by a test. Without them, running the tests would call real APIs, use up the free AI quota and post real alerts.

### 2. A password hash computed once
```python
PASSWORD = "correct-horse"
PASSWORD_HASH = hash_password(PASSWORD)
```
bcrypt is slow on purpose (about 0.3 s per hash on this laptop). Hashing once instead of twice per test cut the suite from 142 s to about 10 s (chapter 9, bug 25).

### 3. Fixtures
| Fixture | Gives the test | Details |
|---|---|---|
| `session_factory` | A fresh in-memory database | `StaticPool` makes every connection share the same in-memory database (otherwise each would get its own empty one). Creates the tables, seeds the 12 venues, and adds `admin@lime-ops.de` and `manager@lime-ops.de`. Thrown away after the test, so tests can't affect each other. |
| `db` | One session on that database | For tests that work with the database directly. |
| `client` | A `TestClient` for the app | `app.dependency_overrides[get_db]` points every endpoint at the test database. This is why `get_db` is a FastAPI dependency and not a global. |
| `manager_headers`, `admin_headers` | `{"Authorization": "Bearer …"}` | Logs in through the **real** login endpoint, so login is tested every time too. |

Test emails use `@lime-ops.de`, because the `email-validator` library rejects reserved domains like `.test` (chapter 9, bug 5).

### 4. Recorded data: `tests/fixtures/ticketmaster_events.json`
A hand-written Ticketmaster response with three events, each there to test one path:
1. A complete VfB match at "MHPArena Stuttgart", with three images of different sizes.
2. A concert with **only a date** (time TBA) at an unknown venue.
3. A broken event with no dates.

Tests never call the real API: it's slow, needs a key, its data changes daily and it has rate limits.

---

## 6.3 `test_ingest.py`: collecting events (8 tests)

| Test | Proves |
|---|---|
| `test_ticketmaster_normalize_full_event` | Every field is mapped: category `sport`, exact UTC start, the **widest** 16:9 image, venue ref, coordinates parsed from strings, address joined. |
| `test_ticketmaster_normalize_date_only_assumes_evening_local_time` | A TBA time becomes 19:00 **Stuttgart** time, which is 18:00 UTC in November. |
| `test_ticketmaster_normalize_skips_event_without_start` | A broken event returns `None` instead of crashing the sync. |
| `test_ticketmaster_fetch_pages_and_windows` | With `MockTransport` as the API: a 30-day range makes **3** requests (14 + 14 + 2 days), sends the right `latlong`, key and **`locale=*`**, and removes events repeated across windows. |
| `test_predicthq_normalize` | Category mapping, attendance, and the GeoJSON **[lng, lat]** coordinate order. |
| `test_upsert_matches_seed_venue_and_creates_unknown` | "MHPArena Stuttgart" matches the seeded "MHPArena" and remembers the API's venue ID; an unknown venue is created once; the second sync **updates** instead of inserting. |
| `test_cross_source_duplicate_links_and_copies_attendance` | The same match from PredictHQ is linked as a duplicate, and its attendance prediction is copied to the primary. |
| `test_runner_records_success_failure_and_skips_disabled` | Three fake connectors (good, failing, disabled): `success`, `failed` without stopping the others, skipped. The API key is **scrubbed** from the stored error. |

`FakeConnector` (defined here, reused by other files) is a tiny `Connector` that returns given events or raises a given error.

## 6.4 `test_venue_matching.py`: venue rules and repairs (8 tests)

Written after the first **real** sync went wrong (chapter 9, bugs 21–24). The coordinates and IDs are real Ticketmaster data.

| Test | Proves |
|---|---|
| `test_name_match_far_away_is_a_different_venue` | Ludwigsburg's "MHP Arena", 11.6 km away, does **not** match Stuttgart's MHPArena. |
| `test_name_match_nearby_links_the_seed_venue` | The real Stuttgart "MHP Arena" does match, and its ID is remembered. |
| `test_named_venue_is_never_matched_by_distance_alone` | The club "Schräglage", 70 m from the Marktplatz, gets its own venue. |
| `test_nameless_venue_still_matched_by_distance` | A venue **without** a name near the Marktplatz is still matched to it. |
| `test_placeholder_is_merged_into_the_matching_venue` | An old "Unknown venue" row is merged into the Schleyerhalle when the name arrives, and **both** of its events move, including one not in the current sync. |
| `test_placeholder_without_known_venue_is_renamed` | A placeholder with no known match keeps its ID and gets the real name. |
| `test_wrong_distance_link_is_dropped` | Marktplatz ← Schräglage, linked under the old rule, is undone. |
| `test_migration_moves_only_untouched_seed_coordinates` | Runs **real Alembic migrations** on a temporary SQLite file: 0003 moves an untouched seed venue, leaves a manager-corrected one alone, and `downgrade` restores the old values. |

## 6.5 `test_deployment.py`: the scooter model (5 tests)

Pure logic with in-memory objects, so there's no database and the tests are very fast.

| Test | Proves |
|---|---|
| `test_attendance_precedence` | Capacity × fill factor; then the API value wins over that; then the manager's value wins over everything; with no venue, the category default. |
| `test_recommendation_scooters_priority_and_windows` | 3,500 × 0.8 = 2,800 visitors → 14 scooters, `medium`, with exact arrival and departure windows. |
| `test_recommendation_is_capped_and_missing_end_defaults_to_three_hours` | 100,000 visitors → capped at 150; with no end time, departures start 3 h after the start. |
| `test_multiday_event_spreads_api_attendance_and_uses_daily_hours` | 30,000 over 3 days → 10,000 a day; a middle day runs 11:00–23:00 local time. |
| `test_hotspots_group_nearby_venues_and_use_peak_overlap` | NeckarPark venues merge into one hotspot. **The overlap case:** A overlaps B, B overlaps C, A and C don't, so the peak is 300, not 330. This test caught the first, wrong algorithm. |

## 6.6 `test_api.py`: the REST API (12 tests)

| Test | Proves |
|---|---|
| `test_requires_auth` | No token or a garbage token → 401. |
| `test_login_rejects_wrong_password` | → 401. |
| `test_me_and_role_checks` | A manager gets 403 on the users and sync endpoints; an admin gets 200. |
| `test_admin_creates_user_who_can_log_in` | Email case is ignored. |
| `test_admin_cannot_demote_self` | → 400 (no locking yourself out). |
| `test_day_view_includes_recommendations_and_hotspots` | The full day response: venue, `capacity` source, `high` priority, capped hotspot. |
| `test_day_boundaries_use_stuttgart_local_time` | 23:30 Stuttgart time on the 7th (22:30 UTC) belongs to the 7th. **The most important timezone test.** |
| `test_duplicates_are_hidden` | Only the primary copy is listed. |
| `test_calendar_summary_and_range_limits` | A 3-day expo appears on each day; over 100 days or an unknown category → 422. |
| `test_manual_event_crud` | Create with a new venue, edit, end-before-start rejected, a time **without a timezone** rejected, delete, then 404. |
| `test_imported_events_only_accept_attendance_override` | Editing or deleting an imported event → 400; a visitor override still works and changes the recommendation. |
| `test_ingest_run_without_sources_is_rejected` | "Sync now" with no key → 400. |

## 6.7 `test_production.py`: production behaviour (13 tests)

| Test | Proves |
|---|---|
| `test_production_refuses_default_secret_and_sqlite` | Production with the default secret or SQLite refuses to start; development allows both. |
| `test_json_log_format` | Each log line is valid JSON with the right fields. |
| `test_health_checks_database` | `/api/health` checks the database. |
| `test_ingest_health` | 503 with no source / never synced / last success 40 h ago / only a failed run; 200 after a recent success. |
| `test_alerts_for_failed_and_empty_syncs` | With `httpx.post` faked: one alert for 0 events, one for a failure, none for a success. |
| `test_broken_webhook_does_not_raise` | A webhook network error doesn't break the sync. |
| `test_run_in_another_process_blocks_new_runs` | A fresh "running" row (as another process would leave) blocks new syncs, and the API answers 409. |
| `test_stale_running_row_is_ignored` | A 3-hour-old "running" row doesn't block. This caught the `db.merge` bug. |
| `test_purge_old_events_keeps_recent_and_removes_dependent_duplicates` | Retention deletes old events and the duplicates pointing at them, and keeps recent ones. |
| `test_audit_fields` | `created_by` and `updated_by` show the right people, including in the day view. |
| `test_bootstrap_admin_only_when_no_users` | The first admin is created only on an empty database; a later start doesn't reset the password. |
| `test_bootstrap_admin_needs_both_settings_and_a_real_password` | Missing email, missing password or a password under 8 characters → no admin. |
| `test_worker_catches_up_when_data_is_stale` | The worker syncs on start only when a source is configured and no success is recent. |

## 6.8 `test_assistant.py`: the AI assistant (34 tests, no real AI calls)

| Group | Tests | Proves |
|---|---|---|
| Tool definitions | `test_tool_specs_match_implementations` | Every tool sent to the model exists, and every existing tool is sent. |
| `search_events` | `..._range_is_inclusive_and_sorted`, `..._filters` | Inclusive end date, sort order, the exact row for the VfB match, filters for venue (including aliases), title text, category and minimum visitors, `limit` with `total` and `shown`, and `last_day` for multi-day events. |
| `get_day_plan` | `test_day_plan_matches_day_view` | **The same numbers as the `/api/events/day` endpoint**, so chat and UI can't disagree. |
| `get_busiest_days`, `list_venues` | `test_busiest_days`, `test_list_venues_matches_aliases` | Ranking by extra scooters; alias search ("schleyer" → Hanns-Martin-Schleyer-Halle). |
| Bad input | `test_tool_errors_are_returned_as_text` ×8 | An unknown tool, bad JSON, "next friday" as a date, a reversed range, over 100 days, category "sports", a missing date, `top="many"`: each returns `Error: …` instead of crashing. |
| Prompt | `test_prompt_spells_out_relative_dates` | For a fixed Monday: the "next week", "this weekend" and "this month" ranges. |
| Tool loop | `test_agent_runs_tools_and_returns_answer` | The fake provider first asks for a tool, then answers. Checks the URL, `Bearer` key, model, system prompt with today's date, tools, the tool result sent back **with the matching `tool_call_id`**, the reply and `tools_used`. |
| | `test_agent_stops_after_max_tool_rounds` | A model that never stops calling tools is cut off. |
| | `test_reply_cleanup_repairs_lenticular_brackets` | `【Sat 24 Oct](…)` → `[Sat 24 Oct](…)`, a quirk seen live from gpt-oss. |
| Provider errors | `test_provider_errors_become_friendly_messages` ×4, `test_connection_error_is_friendly` | 401, 404, 429 (retried twice), 400 and network errors become friendly messages that **never contain the key**. |
| Endpoint | `test_chat_requires_login`, `test_chat_disabled_without_key`, `test_ollama_needs_no_key`, `test_chat_validates_history` ×6, `test_chat_returns_answer`, `test_chat_maps_provider_errors_to_502` | 401 without login; 503 when not configured (and the status endpoint says so); Ollama needs no key, Hugging Face does; 6 invalid histories → 422 (empty, starting with the assistant, two user turns in a row, ending with the assistant, over 4,000 characters, an injected `system` role); the happy path passes the history through; 502 with the friendly message on provider errors. |

The fake provider looks like this:
```python
def handler(request):
    requests.append(json.loads(request.content))
    if len(requests) == 1:   # first call: the model wants a tool
        return httpx.Response(200, json=_completion(_tool_call("call_1", "search_events", {...})))
    return httpx.Response(200, json=_completion({"role": "assistant", "content": "Three events next week."}))

answer(db, settings, history, client=httpx.Client(transport=httpx.MockTransport(handler)), now=NOW)
```
`now=NOW` fixes "today" (Monday 2 Nov 2026), so date-dependent results are the same on every run.

## 6.9 `test_cli.py`: `set-password` (5 tests)

| Test | Proves |
|---|---|
| `test_set_password_changes_login` | After the change, the **new password logs in and the old one doesn't** (through the real login endpoint). The email's case doesn't matter. |
| `test_set_password_rejects_bad_input_without_changes` ×2 | Mismatched repeat; under 8 characters. Each exits with a message and **the stored hash is unchanged**. |
| `test_set_password_unknown_user_lists_existing` | The error lists the existing accounts. |
| `test_set_password_from_env_skips_prompt` | `LIME_USER_PASSWORD` works for scripts and never prompts. |

The `prompts` fixture replaces `getpass.getpass` with a function that returns prepared answers, so an interactive prompt can be tested without typing.

---

## 6.10 Frontend checks

There are no automated frontend unit tests yet; that's a known gap (see 6.13). Instead:

| Check | Command | Catches |
|---|---|---|
| **TypeScript typecheck** (strict mode) | `npm run typecheck` | Wrong field names, missing props, `null` not handled, API type mismatches. `strict`, `noUnusedLocals` and `noUnusedParameters` are on. |
| **Production build** | `npm run build` (runs the typecheck first) | Anything that would break the deployed app; it also shows chunk sizes (lazy loading). |

Run them from `D:\Projects\Lime\frontend`.

## 6.11 Manual and live checks

Some things can only be checked for real. These were done during the build, and are worth repeating after big changes:

| What | How | Found |
|---|---|---|
| **Browser walk-through** | Log in; calendar → day view → map; card ↔ marker selection; forms; admin; **the browser console** | Map not fitted to hotspots; today's highlight looked like a demand colour; the Limy window covering its button |
| **Real Ticketmaster sync** | `python -m app.cli ingest`, then inspect the stored venues | "Unknown venue" (no `locale`), the club matched to the Marktplatz, the Ludwigsburg arena |
| **Real AI model** | Ask fixed questions and compare with the tool output ("ground truth") | A retired model, the wrong language, multi-day ranges, a 10× number error, broken link brackets |
| **Fake AI server** | A 20-line OpenAI-compatible server on localhost, to test the whole UI without a key | `localhost` costing 2 s per call on Windows |
| **Docker stack** | `docker compose up -d --build --wait`, `docker compose ps`, service logs, a scripted end-to-end check through `http://localhost` | The CSP blocking FullCalendar's icon font; the first backup being of an empty database |
| **Migrations on real data** | `upgrade` → `downgrade` → `upgrade` on a copy of the database | (all passed) |
| **Negative checks** | Production start with a weak secret; 12 wrong logins | It refused to start; 429 after 5 attempts |

The scripted Docker end-to-end check (in the scratchpad during the build) called, through `http://localhost`: the page and its security headers, a deep link, health, login, the calendar summary, the sync history, the chat status, one real chat question, and 12 wrong logins.

## 6.12 Continuous integration (`.github/workflows/ci.yml`)

On every push and pull request, GitHub Actions runs three jobs:
1. **backend:** `pip install -r requirements.lock pytest`, then `pytest -q`, then `init-db` on an empty database (migrations apply from scratch).
2. **frontend:** `npm ci`, then `npm run build` (including the typecheck).
3. **docker** (only if both pass): builds the images, starts the whole stack with `--wait`, and smoke-tests `https://localhost/api/health` and the page through Caddy.

> The repository is on GitHub (`Akhil5Xavier/lime-event-planner`). The **first run passed all three jobs** on the first try, which also confirmed the backend on Linux with Python 3.12 and real PostgreSQL. The README shows a live CI badge.

## 6.13 Known gaps

- **No frontend unit tests.** The best next step is **Vitest** (Vite's test runner) for `lib/format.ts`, the Stuttgart-time conversions, where bugs are silent and costly. After that, **React Testing Library** for `useChat` and `LimyWidget`'s `panelStyle()`.
- **No browser end-to-end tests.** **Playwright** could automate the walk-through in 6.11 (log in, open a day, use Limy).
- **AI answer quality** can't be unit-tested. A small "eval" (a fixed set of questions with expected facts, run against the real model) would catch prompt regressions.
- **Postgres-specific behaviour** is only covered by the Docker run and CI; the unit tests use SQLite.

## Checkpoint

1. `pytest -q` shows `85 passed`.
2. **Break something on purpose:** change `ARRIVAL_LEAD` in `deployment.py` to 60 minutes and run again. `test_recommendation_scooters_priority_and_windows` should fail. Change it back. A test suite you've never seen fail is a suite you can't trust.
3. `npm run build` finishes without errors.

Next: [Chapter 7, Frontend](07-frontend.md).
