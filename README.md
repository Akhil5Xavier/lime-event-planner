# Lime Event Planner · Stuttgart

Internal tool for the Lime Stuttgart mobility center. It collects upcoming events in and around Stuttgart, shows them on a calendar, and recommends where and when to put extra e-scooters.

- **Calendar**: month or week view. Each day is coloured by expected demand and shows `events · +extra scooters`.
- **Day view**: event list with a scooter recommendation per event, a deployment plan per hotspot, and a map of the day's venues.
- **Manual events** for things the APIs miss (Volksfest, Weindorf, Christmas market), plus **visitor overrides** on any event.
- **Venues**: managers can correct capacity and add parking notes for the field team.
- **Admin**: data-source status, sync history, "Sync now", user management.

**Want to understand or rebuild it?** [docs/build-guide](docs/build-guide/README.md) explains every file and function, step by step, in the order it was built.

## Architecture

```
Ticketmaster API ─┐
PredictHQ (opt.) ─┼─► nightly ingestion (APScheduler) ─► PostgreSQL ◄─ FastAPI (JWT) ◄─ React SPA (nginx)
Manual entries ───┘
```

| Part     | Stack |
|----------|-------|
| backend  | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, APScheduler, httpx |
| frontend | React 18, TypeScript, Vite, TanStack Query, FullCalendar, Leaflet/OpenStreetMap, Tailwind |
| deploy   | Docker Compose: `caddy` (HTTPS), `frontend` (nginx), `backend` (API), `worker` (nightly sync), `db` (Postgres 16), `backup` |

## Production deployment

### What the stack does

| Service    | Role |
|------------|------|
| `caddy`    | The only service exposed to the network (ports 80/443). Gets and renews a Let's Encrypt certificate for `DOMAIN` automatically and sends an HSTS header. |
| `frontend` | nginx serving the React app. Adds security headers (CSP, X-Frame-Options, …), limits logins to 5 per minute per IP, and proxies `/api` to the backend. |
| `backend`  | FastAPI with `WEB_CONCURRENCY` workers (default 2), running as a non-root user. Applies database migrations on start. Refuses to start if `JWT_SECRET` is weak or the database is SQLite. |
| `worker`   | Runs the nightly sync (`INGEST_CRON`, default 03:00 Stuttgart time) and deletes events older than `EVENT_RETENTION_DAYS`. Exactly one should run. |
| `db`       | PostgreSQL 16; data in the `pgdata` volume. |
| `backup`   | A compressed `pg_dump` into `./backups` at start-up and then every 24 h, keeping `BACKUP_KEEP_DAYS` (14). |

All logs are JSON, one object per line, and rotated at 10 MB × 5 files per service. Image versions and Python packages (`backend/requirements.lock`) are pinned, so a rebuild gives the same result.

### First deployment

1. **Server**: a Linux VM (2 vCPU, 4 GB RAM, 40 GB disk) with Docker and the Compose plugin. Open only ports 80 and 443. If possible, keep it reachable only through the company VPN or SSO proxy.
2. **DNS**: point your host name (e.g. `events.stuttgart.example.com`) at the server.
3. **Code**: `git clone` the repository onto the server.
4. **Config**:
   ```bash
   cp .env.example .env
   ```
   Set `DOMAIN`, `JWT_SECRET` (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`), `POSTGRES_PASSWORD`, `TICKETMASTER_API_KEY` and `ALERT_WEBHOOK_URL`. Store a copy of these values in your password manager.
5. **Start**:
   ```bash
   docker compose up -d --build --wait
   ```
6. **First admin** (prompts for a password):
   ```bash
   docker compose exec backend python -m app.cli create-user you@li.me --role admin
   ```
7. Open `https://<DOMAIN>`, go to **Admin**, click **Sync now**, and add the manager accounts.

### Monitoring

- **Uptime**: point a monitor (UptimeRobot, Better Stack, …) at
  - `https://<DOMAIN>/api/health`: API and database are up;
  - `https://<DOMAIN>/api/health/ingest`: returns 503 if no data source is configured or the last successful sync is older than `INGEST_MAX_AGE_HOURS` (36).
- **Sync alerts**: with `ALERT_WEBHOOK_URL` set (a Slack incoming webhook, or anything that accepts `{"text": "..."}`), every failed sync and every sync that finds 0 events posts a message.
- **Errors**: set `SENTRY_DSN` (backend) and `VITE_SENTRY_DSN` (browser, needs a rebuild) to report errors to Sentry. Both are off when empty.
- **Logs**: `docker compose logs -f backend worker`.

### Backups and restore

Backups land in `./backups/lime-YYYYMMDD-HHMMSS.sql.gz` on the server. **Copy them off the machine too**, for example with a nightly `aws s3 sync ./backups s3://<bucket>/lime-events/`.

Take a backup now:
```bash
docker compose exec backup /ops/backup.sh
```

Restore (the dump drops and recreates the tables). Stop the app first, restore, then start it again:
```bash
docker compose stop backend worker
gunzip -c backups/lime-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T db psql -U lime -d lime
docker compose start backend worker
```
Test a restore at least once a quarter, on a copy of the stack.

### Updating

```bash
git pull
docker compose up -d --build --wait
```
Migrations run automatically when the backend starts. To change Python dependencies, edit `backend/requirements.txt` and regenerate `requirements.lock` (instructions at the top of that file).

### Running everything on your own machine (one command)

**One-time setup (Windows):**
1. In an **administrator** PowerShell, run `wsl --install`, then restart the PC.
2. Install Docker Desktop (`winget install Docker.DockerDesktop`, or from docker.com) and start it once. Docker Desktop is free for personal use and small companies; larger companies need a paid subscription.
3. Create the root `.env` from `.env.example` with:
   - `DOMAIN=http://localhost`;
   - a long random `JWT_SECRET` and a `POSTGRES_PASSWORD`;
   - `ADMIN_EMAIL` and `ADMIN_PASSWORD` for your first login;
   - your `TICKETMASTER_API_KEY` and `LLM_API_KEY`.

**Start**, from the project root (`D:\Projects\Lime`):
```bash
docker compose up -d --build --wait
```
From `D:\Projects\Lime\backend` the same command is:
```bash
docker compose -f ..\docker-compose.yml up -d --build --wait
```

The first build takes a few minutes; after that, starting takes seconds. When the command returns, open **<http://localhost>** and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. On a fresh database the admin is created automatically, and the worker runs a first Ticketmaster sync straight away, so events appear within about a minute.

| Task | Command (from the project root) |
|---|---|
| Logs | `docker compose logs -f backend worker` |
| Set a new password (prompts twice) | `docker compose exec backend python -m app.cli set-password you@example.com` |
| List users | `docker compose exec db psql -U lime -d lime -c "select email, role, is_active from users;"` |
| Stop (keeps data) | `docker compose down` |
| Stop and delete all data | `docker compose down -v` |

## Continuous integration

`.github/workflows/ci.yml` runs on every push:
- backend tests, and migrations applied to an empty database;
- frontend typecheck and build;
- a full `docker compose` stack started and smoke-tested over HTTPS.

## Local development

Backend on SQLite:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy ..\.env.example .env         # then set TICKETMASTER_API_KEY; DATABASE_URL defaults to SQLite
python -m app.cli init-db
python -m app.cli create-user you@li.me --role admin
uvicorn app.main:app --reload --port 8000
```

API docs are at <http://localhost:8000/docs>. Run the tests with `pytest`.

Frontend (needs Node 24 LTS). Vite proxies `/api` to port 8000:

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

**Windows: "DLL load failed … An Application Control policy has blocked this file"** on `import sqlalchemy`. Windows Smart App Control blocks SQLAlchemy's compiled speed-up files (`*_cy*.pyd`). SQLAlchemy works the same without them, so install its pure-Python package instead (same version as the lockfile; stop any running backend first):

```bash
.venv\Scripts\python.exe -m pip download sqlalchemy==2.1.6 --no-deps --only-binary=:all: --platform any --python-version 3.15 --implementation py -d %TEMP%\sqla
.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps %TEMP%\sqla\sqlalchemy-2.1.6-py3-none-any.whl
```

Repeat this after recreating the virtual environment. Docker and Linux aren't affected.

Other CLI commands: `python -m app.cli ingest` runs a sync immediately; `python -m app.cli set-password EMAIL` sets a new password. For a non-interactive `create-user`, set `LIME_USER_PASSWORD`.

## How the recommendation works

The model is kept simple on purpose, so managers can check it and override it:

1. **Visitors** come from the first available of: the manager's override, the data source's prediction (PredictHQ), venue capacity × a category fill factor (sport 0.9, concert 0.8, theatre 0.75, festival 0.6, …), or a category default. For multi-day events, the predicted total is spread over the days.
2. **Extra scooters** = `ceil(visitors × SCOOTER_SHARE)`, default 0.5 %, capped at `MAX_SCOOTERS_PER_SPOT` (150).
3. **Time windows**: arrivals from 90 minutes before the start; departures from the end until 60 minutes after it. If the end time is unknown, 3 hours after the start is assumed. Middle days of multi-day events use 11:00–23:00.
4. **Hotspots**: venues within `HOTSPOT_RADIUS_M` (600 m) of each other form one hotspot. For example, MHPArena, Porsche-Arena and Schleyerhalle are all in NeckarPark. A hotspot's need is the peak of events that overlap in time, not the plain sum, because scooters from an afternoon match can serve an evening concert.
5. **Priority**: high at 10,000+ visitors, medium at 2,000+, otherwise low.

Tune the numbers with the env vars in `.env.example`, or change `backend/app/services/deployment.py`.

## Data sources

- **Ticketmaster Discovery API** (primary, free: 5,000 calls/day). The connector queries a 25 km radius around Stuttgart city centre for the next 90 days, in 14-day windows, to stay under the API's 1,000-result paging limit.
- **PredictHQ** (optional, paid). Turns on automatically when `PREDICTHQ_TOKEN` is set. It adds attendance predictions. Events that both sources report are linked as duplicates (same venue, start within 1 hour, similar title), and only one copy is shown.
- Eventbrite is not used because its public event search API has been retired.
- To add a source, implement `Connector` in `backend/app/ingest/` (`fetch(start, end) -> list[NormalizedEvent]`) and register it in `runner.all_connectors()`.

API venues are matched to the 12 seeded Stuttgart venues:
- by the venue id remembered from an earlier sync;
- by name or alias, but only within 3 km, so the "MHP Arena" in Ludwigsburg doesn't count as Stuttgart's;
- by distance (within 150 m), only for venues that arrive without a name.

Unknown venues are created automatically. Ticketmaster requests send `locale=*`; without it, German-only venues arrive without a name. The seed coordinates come from Ticketmaster where it lists the venue. Capacities are approximate; correct them on the **Venues** page.

## AI assistant (free)

**Limy**, the assistant, is available on every page through a round green button (bottom right). Click it to open a small chat; while the chat is closed you can drag the button anywhere, and the position is remembered. The **Assistant** page is the full-size version, and conversations carry over between the two. Limy answers questions in plain language, for example "Which events are coming up next week?", "What's the busiest day this month?" or "Where should we put extra scooters on Saturday?".

**How it works:** a language model gets four **read-only** tools (`search_events`, `get_day_plan`, `get_busiest_days`, `list_venues`). They call the same code as the calendar and day view, so answers match what the app shows. The model can't change any data. Days in answers link to the day view.

**Set-up (free):**
1. Create a free Groq key at <https://console.groq.com/keys>. No credit card is needed.
2. Add it to `.env` (in `backend\.env` for local development): `LLM_API_KEY=gsk_...`
3. Restart the backend. The Assistant page is enabled automatically.

**Other providers:** any OpenAI-compatible API works. Change `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`; `.env.example` has ready-to-copy blocks for each.

**"Model … was not found":** free providers retire models (Groq dropped the Llama models this project first used). List what your key can use, from `backend`, and set one with tool support as `LLM_MODEL`:
```bash
.venv\Scripts\python.exe -c "import httpx; from app.config import Settings as S; s=S(); print([m['id'] for m in httpx.get(s.llm_base_url+'/models', headers={'Authorization':'Bearer '+s.llm_api_key}).json()['data']])"
```

| Provider | Cost | Notes |
|---|---|---|
| **Groq** (default, `openai/gpt-oss-120b`) | Free tier with daily and per-minute limits | Fast. `qwen/qwen3.8-27b` is an alternative. |
| Google Gemini | Free tier | On the free tier Google may use prompts to improve its products. |
| Hugging Face | Small free monthly credits | Choose a model that supports tool calling. |
| Ollama | Free and fully local | Nothing leaves the machine. Needs RAM: a 7–8B model wants about 8 GB free, and small models are less reliable at tool calling. In Docker, `localhost` means the container itself, so point `LLM_BASE_URL` at the host. |

**Limits and safety:**
- At most 6 tool round trips per question.
- Questions are limited to 4,000 characters, and conversations to 20 turns.
- nginx allows 10 questions per minute per IP, which protects the free quota.
- The API key never appears in logs or error messages.
- Event titles from outside sources are treated as data, not instructions.

**Privacy:** questions and the event data the tools return are sent to the chosen provider. Use Ollama if nothing may leave the company network.

## Operations notes

- In development the scheduler runs inside the API (`SCHEDULER_ENABLED=true`, a single process). In Docker it runs in the `worker` service, and the API can use several workers. Overlapping syncs are blocked across processes through the `ingest_runs` table. A "running" row older than 2 hours is treated as left over from a crash.
- API keys are removed from sync error messages before they are stored or sent as alerts.
- Imported events are overwritten on every sync, so they can't be edited. Only the visitor override (stored separately) survives. Manual events can be fully edited and deleted.
- Every manual event records who added it, and every edit or visitor override records who made it and when. This is shown on the event card.
- Login tokens last 8 hours (`JWT_EXPIRE_MINUTES`). Changing `JWT_SECRET` signs everyone out.
