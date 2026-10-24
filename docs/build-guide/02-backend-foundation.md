# Chapter 2: Backend foundation

In this chapter you build the parts everything else depends on: settings, the database connection, the tables, small geography helpers, passwords and login tokens, and the starting list of Stuttgart venues.

Build order matters: `config.py` has no dependencies, `db.py` needs config, `models.py` needs db, `security.py` needs models.

---

## 2.1 `app/config.py`: all settings in one place

**Purpose:** every value that differs between your laptop and the production server (API keys, database address, tuning numbers) is read from environment variables or a `.env` file, never hard-coded.

**Why:** you must be able to change the database or an API key without editing code, and secrets must never be committed to git.

```python
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    log_format: Literal["text", "json"] = "text"
    sentry_dsn: str | None = None
    database_url: str = "sqlite:///./lime_events.db"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 8 * 60
    ticketmaster_api_key: str | None = None
    predicthq_token: str | None = None
    ingest_cron: str = "0 3 * * *"
    ingest_days_ahead: int = 90
    scheduler_enabled: bool = True
    ingest_max_age_hours: int = 36
    event_retention_days: int = 365
    alert_webhook_url: str | None = None
    timezone: str = "Europe/Berlin"
    city_lat: float = 48.7758
    city_lng: float = 9.1829
    city_radius_km: int = 25
    scooter_share: float = 0.005
    max_scooters_per_spot: int = 150
    hotspot_radius_m: int = 600
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
```

### How `BaseSettings` works
Each class attribute is a setting. Pydantic looks for an environment variable with the same name in upper case (`database_url` → `DATABASE_URL`), then in `.env`, and falls back to the default written here. It also **converts types**: `SCOOTER_SHARE=0.005` in `.env` is a string, but you get a `float`.

- `env_file=".env"` reads `.env` from the current folder, which is why you run the backend from `backend/`.
- `extra="ignore"` means unknown variables in `.env` (like `DOMAIN`, which only Docker uses) don't cause errors.
- `Literal["development", "production"]` rejects typos: `ENVIRONMENT=prod` fails at startup instead of silently behaving as development.

### Why each setting exists
| Setting | Why |
|---|---|
| `environment` | Turns on the strict production safety checks (below). |
| `log_format` | `json` in production so a log system can search it; `text` locally so humans can read it. |
| `database_url` | SQLite file by default so development needs no setup. |
| `jwt_secret` | The key that signs login tokens. Anyone who knows it can forge a login. |
| `jwt_expire_minutes` | 8 hours, roughly a work day. Shorter means a stolen token is useful for less time. |
| `ingest_cron` | When the nightly sync runs, in cron syntax: minute hour day month weekday, so `0 3 * * *` is 03:00 every day. |
| `ingest_days_ahead` | How far ahead to fetch. 90 days is enough for planning. |
| `scheduler_enabled` | Whether the API process runs the scheduler (true in development; false in production, where a separate worker runs it). |
| `ingest_max_age_hours` | If the last successful sync is older than this, the health check reports a problem. 36 = one missed night plus margin. |
| `city_lat/lng/radius` | Centre of Stuttgart and the search radius. 25 km includes Ludwigsburg, Esslingen and the airport/Messe. |
| `scooter_share` | 0.5% of visitors are assumed to want a scooter. A starting guess to be tuned with real ride data. |
| `max_scooters_per_spot` | Cap, because you can't physically place 300 scooters at one street corner. |
| `hotspot_radius_m` | Venues closer than this count as one spot. 600 m groups MHPArena, Porsche-Arena and Schleyerhalle. |
| `cors_origins` | Which browser origins may call the API directly in development (Vite on 5173). |

### `production_problems()` and `check_production()`

```python
    def production_problems(self) -> list[str]:
        problems = []
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            problems.append(f"JWT_SECRET must be a random string of at least {MIN_JWT_SECRET_LENGTH} characters")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL, not SQLite")
        return problems

    def check_production(self) -> None:
        if self.environment == "production" and (problems := self.production_problems()):
            raise RuntimeError("Refusing to start with unsafe production config: " + "; ".join(problems))
```

- `production_problems` **lists** what's unsafe without deciding what to do about it. The API uses that list to log a warning in development.
- `check_production` **refuses to start** in production. "Fail fast": it's far better for a deployment to crash on start with a clear message than to run for months with a guessable token secret.
- `:=` is the "walrus" operator: it assigns and tests in one expression.

### `get_settings()`

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`@lru_cache` remembers the return value, so settings are read once and the same object is returned on every call. FastAPI can also inject it into endpoints with `Depends(get_settings)`, which lets tests swap it out.

---

## 2.2 `app/db.py`: database connection

### `UTCDateTime`: the timezone-safe column type

```python
class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime passed to UTCDateTime column")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
```

**The problem it solves:** times are the most common source of bugs in a calendar app. An event at 23:30 in Stuttgart is 22:30 UTC in winter and 21:30 UTC in summer. If you mix "naive" datetimes (no timezone) with "aware" ones (with timezone), Python either crashes when comparing them or silently gives the wrong answer.

**The rule this enforces:** *store everything in UTC, always aware, and convert to Stuttgart time only for display.*

- `TypeDecorator` wraps a normal column type with custom conversion.
- `process_bind_param` runs when **saving**. It refuses naive datetimes (a bug should crash loudly) and converts to UTC.
- `process_result_value` runs when **loading**. SQLite doesn't store timezones and returns naive values, so this re-attaches UTC. Postgres returns aware values, possibly in another zone, so they're converted to UTC. Either way, the rest of the code always gets aware UTC datetimes.
- `cache_ok = True` tells SQLAlchemy this type is safe to cache in compiled queries.

### `Base`, engine and sessions

```python
class Base(DeclarativeBase):
    pass

def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- **`Base`**: every table class inherits from it. SQLAlchemy collects all tables on `Base.metadata`, which tests and Alembic use.
- **Engine**: manages the pool of connections to the database.
  - `check_same_thread=False`: SQLite normally refuses use from a thread other than the one that opened it. FastAPI runs requests in a thread pool, so this is needed.
  - `pool_pre_ping=True`: before reusing a pooled connection, check it's still alive. Postgres closes idle connections, and without this the first request after a quiet night would fail.
- **`SessionLocal`**: a factory for sessions. A session is one "conversation" with the database: you load objects, change them, and `commit()`.
  - `expire_on_commit=False`: after commit, objects keep their loaded values. Otherwise reading `event.title` after commit would trigger another query, or fail if the session is closed.
- **`get_db()`**: a FastAPI *dependency*. Each request gets its own session, and `finally` guarantees it's closed even if the request crashes. `yield` hands the session to the endpoint; the code after `yield` runs when the request is done.

---

## 2.3 `app/models.py`: the tables

```python
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

CATEGORIES = ("concert", "sport", "theatre", "festival", "expo", "conference", "film", "community", "other")
```

`utcnow` is passed as `default=utcnow` (the function, not its result) so it's called fresh for every row. `default=datetime.now()` would give every row the server start time: a classic mistake.

`CATEGORIES` is the fixed list of event types every source is mapped into, so filters and fill factors work the same whatever the source.

### `Venue`

| Column | Why |
|---|---|
| `id` | Primary key. |
| `name` (indexed) | Shown everywhere, and searched when matching API venues. |
| `address`, `lat`, `lng` | Shown to managers and used for the map and distance calculations. |
| `capacity` | Used to estimate visitors when the API gives no prediction. Nullable because unknown venues start without one. |
| `aliases` | Pipe-separated alternative names (`"Schleyerhalle\|Schleyer-Halle"`) so different spellings from APIs match the same venue. |
| `scooter_zone_note` | Free text for the field team ("park on Mercedesstraße, not the plaza"). |
| `external_ref` | `"ticketmaster:<id>"`, remembered after the first match, so the next sync matches instantly by ID. |

`events: Mapped[list["Event"]] = relationship(back_populates="events")` lets you write `venue.events` and `event.venue` in Python instead of writing joins.

### `Event`

```python
class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_event_source_external"),)
```

| Column | Why |
|---|---|
| `source` + `external_id` (unique together) | Which API it came from and that API's ID. The unique constraint means a re-sync **updates** the row instead of creating a duplicate. |
| `title`, `category`, `description`, `url`, `image_url` | Display. |
| `start_at`, `end_at` (`UTCDateTime`) | When. `end_at` is nullable because many API events have no end time. |
| `venue_id` | Foreign key to `venues`. |
| `expected_attendance` | The API's prediction (PredictHQ), if any. |
| `attendance_override` | The manager's own estimate. Stored **separately** from API data so a re-sync never overwrites it. |
| `is_manual` | Added by a manager. Only these may be edited and deleted. |
| `duplicate_of_id` | Points to the "primary" copy when two sources report the same event, so it's shown once. |
| `created_by_id`, `updated_by_id` | Audit trail: who added or last changed it (added in migration 0002). |
| `created_at`, `updated_at` | `onupdate=utcnow` refreshes `updated_at` on every change automatically. |

The two user relationships need `foreign_keys=[...]` because `Event` has two foreign keys to `users`, and SQLAlchemy can't guess which one each relationship uses:

```python
created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
updated_by: Mapped["User | None"] = relationship(foreign_keys=[updated_by_id])
```

The foreign keys are given explicit names (`name="fk_events_created_by"`) because SQLite migrations need named constraints to alter tables later.

### `User`
`email` (unique), `name`, `password_hash` (never the password itself), `role` (`admin` or `manager`), `is_active`. Users are deactivated, never deleted, so audit references (`created_by_id`) stay valid.

### `IngestRun`
One row per data source per sync: `source`, `trigger` (`schedule`, `manual` or `cli`), `started_at`, `finished_at`, `status` (`running`, `success` or `failed`), counters (`fetched`, `created`, `updated`, `duplicates`) and `error`.

**Why store this?** It's the Admin page's sync history, the health check's "last successful sync", and the cross-process lock: a `running` row means "a sync is in progress".

### `Mapped[...]` and `mapped_column(...)`
This is SQLAlchemy 2.0 style. `Mapped[str | None]` means the column is nullable; `Mapped[str]` means NOT NULL. Your editor understands these types, so `event.title` autocompletes and type-checks.

---

## 2.4 `app/geo.py`: distance and names

### `haversine_m(lat1, lng1, lat2, lng2)`
Returns the distance in metres between two coordinates, using the haversine formula (distance along the Earth's surface, assuming a sphere of radius 6,371 km).

**Why not just subtract coordinates?** One degree of longitude is about 111 km at the equator but about 73 km in Stuttgart. Plain subtraction would get distances wrong by direction. Haversine is accurate to well under 1% at city scale.

**Used for:** matching an API venue to a known venue within 150 m, and grouping venues within 600 m into one hotspot.

### `normalize_name(name)`
```python
def normalize_name(name: str) -> str:
    s = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", s)
```
`"Hanns-Martin-Schleyer-Halle"` → `"hannsmartinschleyerhalle"`, and `"Schloßplatz"` → `"schlossplatz"`. This makes venue names comparable regardless of case, hyphens, spaces and German spelling variants (ß/ss, ü/ue).

---

## 2.5 `app/security.py`: passwords and login tokens

### `hash_password(password)` and `verify_password(password, hash)`
```python
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False
```
- **Never store passwords.** Store a *hash*: a one-way scramble. On login, hash the typed password the same way and compare.
- **bcrypt** is slow on purpose and adds a random *salt* per password. Salting means two users with the same password get different hashes; slowness makes guessing billions of passwords impractical if the database ever leaks.
- `.encode()` turns text into bytes, which bcrypt needs.
- `except ValueError: return False` means a corrupted hash in the database counts as "wrong password" instead of crashing the login endpoint.

> Many tutorials use the `passlib` library. It's unmaintained and breaks with bcrypt 4+, so this project calls `bcrypt` directly.

### `create_access_token(user)`
```python
payload = {"sub": str(user.id), "role": user.role, "iat": now,
           "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
```
A **JWT** (JSON Web Token) is a small signed message: "user 5, role admin, expires at 18:00", plus a signature made with `JWT_SECRET`. The browser sends it with every request. The server checks the signature, so nobody can edit the user ID without knowing the secret, and it needs no session table in the database.

- `sub` (subject) is the user ID; JWT requires a string.
- `iat` is "issued at" and `exp` is the expiry. PyJWT rejects expired tokens automatically.
- **HS256** means HMAC with SHA-256: one shared secret both signs and checks. That's right when the same server does both.

### `get_current_user(...)`
```python
def get_current_user(creds = Depends(_bearer), db = Depends(get_db)) -> User:
    if creds is None: raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active: raise unauthorized
    return user
```
This is a FastAPI dependency: any endpoint that declares `Depends(get_current_user)` requires a valid login.

- `HTTPBearer(auto_error=False)` reads the `Authorization: Bearer <token>` header. `auto_error=False` lets you return a consistent 401 yourself.
- `algorithms=["HS256"]` must be given explicitly. Otherwise an attacker could send a token claiming algorithm "none".
- It **looks the user up again** in the database. A deactivated user's still-valid token is then refused immediately; you don't have to wait for it to expire.
- Every failure returns the same 401 "Not authenticated", so an attacker learns nothing from the error.

### `require_admin(user)`
Builds on `get_current_user` and returns 403 Forbidden unless `role == "admin"`. 401 means "who are you?" and 403 means "I know who you are, and you're not allowed."

---

## 2.6 `app/seed/venues.py`: the starting venues

`STUTTGART_VENUES` is a list of 12 dictionaries: MHPArena, Porsche-Arena, Hanns-Martin-Schleyer-Halle, Cannstatter Wasen, Liederhalle, Messe Stuttgart, Schlossplatz, Marktplatz, LKA-Longhorn, Im Wizemann, Theaterhaus and Staatstheater. Each has an approximate address, coordinates, capacity and aliases.

**Why seed venues?** Ticketmaster rarely gives capacities. Without a capacity, the recommendation falls back to rough category defaults. The big venues drive most scooter demand, so knowing them well matters most. Aliases like `"Volksfest|Frühlingsfest"` for the Wasen make API names match.

### `seed_venues(db)`
```python
existing = set(db.scalars(select(Venue.name)))
for data in STUTTGART_VENUES:
    if data["name"] in existing:
        continue
    db.add(Venue(**data))
```
It only adds venues that don't exist yet. That makes it **idempotent**: safe to run on every startup without creating duplicates, and it won't overwrite capacities a manager has corrected.

To fill in this list yourself, look up each venue on OpenStreetMap (right-click → "Show address" shows the coordinates) and its official capacity.

## Checkpoint

```powershell
.venv\Scripts\python.exe -c "from app.models import Base; print(sorted(Base.metadata.tables))"
```
Expected output: `['events', 'ingest_runs', 'users', 'venues']`.

```powershell
.venv\Scripts\python.exe -c "from app.security import hash_password, verify_password as v; h=hash_password('secret123'); print(v('secret123', h), v('wrong', h))"
```
Expected output: `True False`.

Next: [Chapter 3, Data collection](03-data-collection.md).
