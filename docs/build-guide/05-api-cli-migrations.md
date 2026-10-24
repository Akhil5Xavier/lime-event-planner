# Chapter 5: API, CLI and migrations

This chapter exposes everything over HTTP, wires the app together, and adds the admin command line and database migrations.

---

## 5.1 `app/schemas.py`: what goes in and out of the API

Schemas are **Pydantic models** describing the JSON the API accepts and returns. FastAPI uses them to:
- **validate input**, rejecting a missing title or a negative visitor count with a clear 422 error before your code runs;
- **shape output**, sending only the listed fields. A user's `password_hash` can never leak, because `UserOut` doesn't include it;
- **document the API** at `/docs` automatically.

**Why separate schemas from the database models?** The API contract and the table layout change for different reasons. `EventIn` has a `new_venue` field that isn't a column; `EventOut` includes a nested venue and users.

Key pieces:

```python
Category = Literal["concert", "sport", ...]
Role = Literal["admin", "manager"]
Priority = Literal["low", "medium", "high"]

class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```
`from_attributes=True` lets a schema be built straight from a SQLAlchemy object (or a dataclass such as `Recommendation`), reading its attributes. Output schemas inherit from `ORM`.

| Schema | Used for | Notes |
|---|---|---|
| `LoginIn` | login request | `email` is a plain `str`, not `EmailStr`. Strict validation rejected reserved test domains like `.test`, and login doesn't need it; wrong input simply fails to log in. |
| `UserOut`, `TokenOut` | login response, user lists | Never includes the password hash. |
| `UserCreate`, `UserUpdate` | admin user management | `password: str = Field(min_length=8)`. All fields optional in the update schema, for partial updates. |
| `VenueIn`, `VenueUpdate`, `VenueOut` | venues | `lat: float = Field(ge=-90, le=90)` rejects impossible coordinates. |
| `UserBrief` | nested in events | id, email, name: just enough to show "added by". |
| `EventOut` | every event response | Includes `venue`, `created_by`, `updated_by` and `updated_at`. |
| `EventIn` | creating a manual event | **`start_at: AwareDatetime`**: a time without a timezone is rejected. `new_venue` lets the form create a venue in the same request. |
| `EventUpdate` | editing | All fields optional. |
| `AttendanceOverrideIn` | the manager's visitor estimate | `None` removes the override. |
| `WindowOut`, `RecommendationOut`, `HotspotOut` | recommendations | Built from the dataclasses in chapter 4. |
| `DayEventOut` | day view | `EventOut` plus `recommendation`. |
| `DaySummary`, `DayOut`, `CalendarDayOut` | day view and calendar colouring | |
| `IngestRunOut`, `SourceStatus` | admin page | |

---

## 5.2 The routers in `app/api/`

Each file creates an `APIRouter` with a URL prefix. Auth is applied **at router level** where every endpoint needs it:
```python
router = APIRouter(prefix="/api/venues", tags=["venues"], dependencies=[Depends(get_current_user)])
```
You can't forget the login check on a new endpoint, because the whole router has it.

### `auth.py`
- **`POST /api/auth/login`**: finds the user by lower-cased email (`func.lower(User.email) == body.email.lower()`, so "Admin@…" works too) and checks it's active and the password matches. It returns the same "Invalid email or password" for every failure, so an attacker can't learn which emails exist. On success it returns a token and the user.
- **`GET /api/auth/me`**: returns the logged-in user. The frontend uses it to show the name and admin menu.

### `users.py` (whole router is admin-only)
- **`GET /api/users`**: lists users.
- **`POST /api/users`**: creates a user. Returns 409 if the email exists. Emails are stored lower-case.
- **`PATCH /api/users/{id}`**: changes name, role, active status or password. **An admin can't demote or deactivate themselves**, which prevents locking every admin out by accident.

### `venues.py`
- **`GET /api/venues`**, **`POST /api/venues`**, and **`PATCH /api/venues/{id}`** with `model_dump(exclude_unset=True)`. Only fields actually sent are changed, so sending `{"capacity": 5000}` doesn't wipe the address.

### `events.py`: the main router
Helpers:
- `_categories(text)`: parses `?category=sport,concert` and rejects unknown names with 422.
- `_range(db, start, end, category, tz)`: validates the range (end after start, at most 100 days, to protect the server from huge queries), converts local dates to UTC bounds and calls `events_between`.
- `_summarize(events, day, settings)`: builds recommendations and hotspots and computes the day summary. **Total extra scooters = the sum of hotspot needs**, not of event needs, so the peak logic applies. Events without a venue are added on top.
- `_get_event`, `_require_manual`, `_check_venue`: small checks returning 404, 400 or 422.

Endpoints:
| Endpoint | What | Why it looks like this |
|---|---|---|
| `GET /api/events?start=&end=&category=` | Events overlapping a range of local dates (end exclusive) | Feeds the calendar's event list. Dates, not datetimes, because the calendar thinks in days. |
| `GET /api/events/summary?start=&end=` | One row per day: count, visitors, scooters, priority | Colours the calendar cells. Multi-day events are counted on every day they run. |
| `GET /api/events/day/{date}` | Everything for one day: events with recommendations, hotspots, summary | One request gives the whole day view. |
| `GET /api/events/{id}` | One event | |
| `POST /api/events` | Create a manual event | `source="manual"`, a random `external_id` (`uuid4().hex`) to satisfy the unique constraint, `is_manual=True`, and `created_by` and `updated_by` set to the current user. |
| `PATCH /api/events/{id}` | Edit | **Manual events only.** Imported events would be overwritten by the next sync, so editing them would be misleading. Sets `updated_by`. |
| `PUT /api/events/{id}/attendance` | Set or clear the visitor override | Works on **all** events and survives syncs. PUT because it replaces one value. |
| `DELETE /api/events/{id}` | Delete | Manual only: an imported event would just come back at the next sync. |

> The `/summary` and `/day/...` routes are declared before `/{event_id}`, and `event_id` is typed `int`, so "summary" can never be mistaken for an ID.

### `ingest.py` (admin-only)
- **`GET /api/ingest/sources`**: which connectors are configured.
- **`GET /api/ingest/runs`**: sync history, newest first, at most 200.
- **`POST /api/ingest/run`**: returns 409 if a sync is running and 400 if no source is configured. Otherwise it starts the sync **in the background** (`BackgroundTasks`) and returns **202 Accepted** immediately. A sync takes about 30 seconds, and HTTP requests shouldn't hang that long. The frontend polls the runs list to show progress.

### `health.py` (no login, so monitors can call it)
- **`GET /api/health`**: runs `SELECT 1`. 200 means the API *and* the database are working; 503 means not. Docker's healthcheck uses it.
- **`GET /api/health/ingest`**: 503 if no source is configured, or if the newest **successful** run is older than 36 hours. This catches the silent failure where everything is "up" but the data is stale.

---

## 5.3 `app/observability.py`

### `JsonFormatter`
Formats each log line as one JSON object with `time`, `level`, `logger`, `message` and `exception`. Log systems (Loki, CloudWatch, Datadog) can then filter by level or search messages.

### `setup_logging(settings)`
Installs one handler, JSON or text, on the root logger, and **re-routes uvicorn's own loggers** to it (`handlers = []`, `propagate = True`). Without this, uvicorn's access logs would keep their own format and your logs would mix two formats.

### `setup_sentry(settings)`
Initialises Sentry only when `SENTRY_DSN` is set. The import is inside the function, so nothing loads when it's unused. `send_default_pii=False` keeps user data out of error reports.

---

## 5.4 `app/main.py`: the entry point

```python
settings = get_settings()
setup_logging(settings)
setup_sentry(settings)

@asynccontextmanager
async def lifespan(app):
    settings.check_production()              # crash on unsafe production config
    if settings.environment != "production" and settings.production_problems():
        log.warning("Development config in use (...)")
    scheduler = start_scheduler() if settings.scheduler_enabled else None
    yield                                    # the app runs here
    if scheduler: scheduler.shutdown(wait=False)

app = FastAPI(title="Lime Stuttgart Event Planner", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, ...)
for module in (health, auth, users, venues, events, ingest):
    app.include_router(module.router)
```
- **`lifespan`**: code before `yield` runs at startup and after it at shutdown. This is FastAPI's replacement for the old `@app.on_event("startup")`.
- **CORS**: browsers block a page on one origin (port 5173) from calling an API on another (port 8000) unless the API allows it. In production everything is served from one origin through nginx, so CORS doesn't come into play.

Run it:
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
`app.main:app` means "the `app` object in module `app.main`". `--reload` restarts on code changes (development only). Open <http://localhost:8000/docs> for interactive API docs.

---

## 5.5 `app/scheduler.py`

- **`nightly_job()`**: runs the sync (skipping quietly if one is already running), then `purge_old_events`.
- **`_configure(scheduler)`**: adds the job with `CronTrigger.from_crontab(INGEST_CRON, timezone="Europe/Berlin")`.
  - `max_instances=1`: never run two copies at once.
  - `coalesce=True`: if several runs were missed (for example the server was off), run once, not five times.
  - `misfire_grace_time=3600`: if the process was busy or restarting at 03:00, still run up to an hour late.
- **`start_scheduler()`**: a `BackgroundScheduler`, which runs in a thread inside the API process. Used in development.
- **`run_worker()`**: a `BlockingScheduler`, which takes over the process. Used by the separate `worker` service in production.

**Why a separate worker in production?** With several API processes (for speed), each would run its own scheduler and the sync would run several times. One dedicated worker runs it exactly once.

---

## 5.6 `app/cli.py`: admin commands

`argparse` sub-commands, run as `python -m app.cli <command>`:

| Command | Function | What and why |
|---|---|---|
| `init-db` | `init_db()` | Runs Alembic migrations to the latest version, then `seed_venues`. Safe to run repeatedly; the Docker container runs it on every start. |
| `create-user EMAIL --role admin --name "…"` | `create_user()` | Creates the **first** admin. There's no sign-up page, on purpose. The password is read with `getpass` (not echoed, not saved in shell history), or from `LIME_USER_PASSWORD` for scripts. |
| `ingest` | `ingest()` | Runs a sync now and prints one line per source. Handy for testing a new API key. |
| `scheduler` | `scheduler()` | Production worker: checks the production config, sets up logging and Sentry, then `run_worker()`. |

---

## 5.7 Alembic migrations

**Why migrations?** In development you could drop and recreate tables, but in production the tables hold real data. When you add a column (like `created_by_id`), you need a script that changes the existing table **without losing data**, applied in order, exactly once. Alembic records the current version in an `alembic_version` table.

### Set-up files
- **`alembic.ini`**: points to the `alembic/` folder. The database URL is *not* here, so there's no second place to configure it.
- **`alembic/env.py`**: imports `app.models` (which registers the tables), sets the URL from `get_settings().database_url` and uses `target_metadata = Base.metadata`. **`render_as_batch=True`** matters for SQLite, which can't alter columns or constraints in place; batch mode copies the table, changes the copy and swaps it in.
- **`alembic/script.py.mako`**: the template for new migration files. It imports `app.db` because migrations reference the custom `UTCDateTime` type.

### Creating migrations
After changing `models.py`:
```powershell
$env:DATABASE_URL = "sqlite:///./autogen.db"
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe revision --autogenerate -m "event audit fields" --rev-id 0002
```
Autogenerate compares your models with the database and writes the difference. **Always read the generated file**; autogenerate can miss things such as renames, which it sees as drop + add and which would lose data.

- `0001_initial_schema.py`: creates the four tables and their indexes.
- `0002_event_audit_fields.py`: adds `created_by_id` and `updated_by_id` with named foreign keys. Its `downgrade()` reverses it.

Test every migration both ways on a copy of real data:
```powershell
alembic upgrade head; alembic downgrade 0001; alembic upgrade head
```

## Checkpoint

```powershell
.venv\Scripts\python.exe -m app.cli init-db
.venv\Scripts\python.exe -m app.cli create-user you@example.com --role admin
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
Then open <http://localhost:8000/docs>:
1. Call `POST /api/auth/login` and copy the token.
2. Click **Authorize** and paste it.
3. Call `GET /api/venues`. You should get 12 venues.

Next: [Chapter 6, Backend tests](06-backend-tests.md).
