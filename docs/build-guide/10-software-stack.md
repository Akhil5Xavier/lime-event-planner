# Chapter 10: The complete software stack

Every piece of software the project uses: the exact version, what it does here, and why it was chosen. Versions are as installed and pinned in October 2026 (`backend/requirements.lock`, `frontend/package-lock.json`, and the image tags in the Dockerfiles and `docker-compose.yml`).

## 10.1 The whole system at a glance

```
                         ┌──────────────────────── Browser (Chrome / Edge / Firefox) ───────────────────────┐
                         │ React 18.3 SPA · TypeScript 5.9 · Tailwind 3.4 · FullCalendar 6.1 · Leaflet 1.9 │
                         │ TanStack Query 5 · React Router 6                                               │
                         └───────────────────────────────────────┬──────────────────────────────────────────┘
                                                                 │ http://localhost  (https://<domain> in production)
┌──────────────────────────────── Docker Compose v5.6 on Docker Engine 29.9 (Docker Desktop 4.96 + WSL 2) ──────────────┐
│  caddy 2.11.7  ──►  frontend: nginx 1.30.6 (static app, CSP, rate limits)  ──► /api ──►  backend: Python 3.12.15      │
│  (ports 80/443,                                                                          FastAPI 0.162 · Uvicorn 0.54 │
│   auto-HTTPS)                                                                            SQLAlchemy 2.1 · Pydantic 2.14│
│                                                                                                 │                      │
│  worker: same image, APScheduler 3.11 (nightly sync) ─────────────────────────────────────────┤                      │
│  backup: pg_dump (postgres 16.15 image) ────────────────────────────────────────────────────► db: PostgreSQL 16.15   │
└────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────┘
                                                                                                 │ HTTPS (httpx 0.28)
                       Ticketmaster Discovery API v2 · PredictHQ (optional) · Slack webhook · Sentry
```

## 10.2 Development machine

| Software | Version | Role in this project | Why |
|---|---|---|---|
| Windows 11 Home | 10.0.26200 | Development OS | The machine this was built on. |
| PowerShell | 5.1 | Shell for all commands in this guide | Built into Windows. |
| Git for Windows | 2.56.0 | Version control; also gives a Bash shell | Standard. `.gitattributes` keeps Linux files LF. |
| Python | 3.15.1 (local) / **3.12.15 (Docker, CI)** | Runs the backend and tests | Docker uses 3.12, where every library has prebuilt packages; locally 3.15 works with a few workarounds (chapter 9). |
| Node.js | 24.20.0 LTS | Runs Vite and TypeScript (development and build only) | LTS = long-term support. Node 20 reached end-of-life in April 2026. |
| npm | 11.19.0 | Installs frontend packages | Comes with Node. |
| Docker Desktop | 4.96.3 | Runs the production stack locally | One-command start. **Free for personal use and small companies; organisations with more than 250 employees or $10M revenue need a paid subscription.** |
| WSL 2 | 3.0.3 (kernel 6.18) | Linux layer Docker Desktop needs on Windows Home | Required by Docker Desktop. |
| winget | (built in) | Installed Node, Git and Docker Desktop | Windows' package manager. |
| VS Code | any | Editor (recommended) | |

## 10.3 Backend (Python)

### Direct dependencies (`backend/requirements.txt` → pinned in `requirements.lock`)

| Package | Version | Role in this project | Why this one |
|---|---|---|---|
| **FastAPI** | 0.162.0 | The REST API: routing, dependencies (`Depends`), validation, `/docs` | Fast, typed, automatic validation and API docs. |
| **Starlette** | 1.10.0 | The web layer under FastAPI (requests, responses, CORS, `TestClient`) | Comes with FastAPI. |
| **Uvicorn** | 0.54.0 | The server process running FastAPI | Standard for FastAPI. The plain version is used, because `uvicorn[standard]` needed a C compiler on Python 3.15. |
| **Pydantic** | 2.14.1 | Request/response schemas (`schemas.py`), validation | Used by FastAPI; strict typing. Its core (`pydantic_core` 2.50.1) is written in Rust. |
| **pydantic-settings** | 2.16.1 | `config.py`: settings from environment variables and `.env` | Typed settings with defaults. |
| **SQLAlchemy** | 2.1.6 | ORM: models, queries, sessions | The standard Python ORM; works on both SQLite and PostgreSQL. Installed locally as the **pure-Python wheel** because Windows Smart App Control blocked its compiled parts (chapter 9). |
| **Alembic** | 1.20.1 | Database migrations 0001–0003 | SQLAlchemy's migration tool. Uses **Mako** 1.4.3 for its file template. |
| **psycopg** (+ psycopg-binary) | 3.3.6 | PostgreSQL driver | Modern, maintained driver; the binary package needs no compiler. |
| **httpx** | 0.28.1 | Calls Ticketmaster, PredictHQ and the alert webhook; `MockTransport` in tests | Timeouts, a sync API and built-in test transports. |
| **APScheduler** | 3.11.3 (pinned `<4`) | The nightly sync (cron 03:00) and the start-up catch-up sync | Runs inside the app, no external cron. v4 is a rewrite, hence the pin. |
| **PyJWT** | 2.15.1 | Login tokens (HS256) | Small and focused. |
| **bcrypt** | 5.0.0 | Password hashing | Slow on purpose, salted, industry standard. Used directly, because `passlib` is unmaintained. |
| **email-validator** | 2.3.0 | Validates emails in the admin user form | Used by Pydantic's `EmailStr`. Uses **dnspython** 2.9.0. |
| **tzdata** | 2026.5 | Timezone database (Europe/Berlin) | Windows has none built in; `zoneinfo` needs it. |
| **sentry-sdk** | 2.73.0 | Optional error reporting (`SENTRY_DSN`) | Off unless configured. |

### Notable indirect dependencies
| Package | Version | Pulled in by | Role |
|---|---|---|---|
| anyio | 4.15.1 | Starlette, httpx | Async/thread support |
| httpcore, h11 | 1.0.9, 0.16.0 | httpx, Uvicorn | HTTP/1.1 protocol |
| certifi, idna, urllib3 | 2026.10.23, 3.20, 2.8.0 | httpx, Sentry | TLS certificates, international domain names |
| tzlocal | 5.4.5 | APScheduler | Local timezone detection |
| python-dotenv | 1.2.4 | pydantic-settings | Reads `.env` files |
| click | 8.5.0 | Uvicorn | Command-line parsing |
| opentelemetry-api | 1.45.1 | sentry-sdk | Tracing interfaces |
| MarkupSafe | 3.0.4 | Mako | Safe string escaping |

### Python standard library modules that matter
`zoneinfo` (timezones), `datetime`, `difflib.SequenceMatcher` (duplicate title similarity), `dataclasses`, `argparse` (the CLI), `getpass` (hidden password prompts), `secrets` (random secrets), `threading` (the in-process sync lock), `logging` + `json` (JSON logs), `math` (haversine distance, `ceil`).

## 10.4 Frontend (TypeScript / React)

### Runtime packages (shipped to the browser)
| Package | Version | Role in this project | Why |
|---|---|---|---|
| **React** + react-dom | 18.3.1 | The whole UI | Most widely used UI library. Version 18 because react-leaflet 4 needs it. |
| **React Router** (react-router-dom) | 6.30.6 | Pages and URLs (`/day/2026-11-07`), protected routes, lazy routes | Shareable links per day. |
| **TanStack Query** (@tanstack/react-query) | 5.104.5 | Fetching and caching API data; refresh after changes; polling the sync status | Removes hand-written loading and caching code. |
| **FullCalendar** (core, react, daygrid, interaction) | 6.1.22 | The month/week calendar | Mature calendar; it ships its icons as an embedded font (CSP needs `font-src data:`). |
| **Leaflet** + react-leaflet | 1.9.4 + 4.2.1 | Day-view map, location picker | Free, open source. |
| **@sentry/react** | 10.76.2 | Optional browser error reporting | Removed from the build when `VITE_SENTRY_DSN` is empty. |

### Build-time packages (not shipped)
| Package | Version | Role |
|---|---|---|
| **TypeScript** | 5.9.3 | Type checking in `strict` mode (`npm run typecheck`) |
| **Vite** | 5.4.21 | Dev server with hot reload and `/api` proxy; production build with code splitting |
| @vitejs/plugin-react | 4.7.0 | JSX and Fast Refresh for Vite |
| **Tailwind CSS** | 3.4.19 | Utility CSS; only the classes actually used are kept |
| PostCSS + Autoprefixer | 8.5.31 + 10.6.1 | Runs Tailwind; adds browser prefixes |
| @types/react, @types/react-dom, @types/leaflet | 18.3.31, 18.3.7, 1.9.22 | Type definitions |

### Browser APIs used
`fetch`, `localStorage` (login token), `Intl.DateTimeFormat` (Stuttgart time), `ResizeObserver` (map refit), `history` (routing).

## 10.5 Containers and infrastructure

| Component | Image / version | Role | Why |
|---|---|---|---|
| **Docker Engine** | 29.9.2 | Runs the containers | Standard. |
| **Docker Compose** | v5.6.1 | Defines and starts all six services (`docker-compose.yml`) | One command. |
| backend / worker image | `python:3.12.15-slim` | API (2 Uvicorn workers, non-root user) and the scheduler worker | Small Debian image with prebuilt wheels. |
| frontend build stage | `node:24.20.0-alpine` | `npm ci && npm run build` | Not in the final image (multi-stage build). |
| frontend image | `nginx:1.30.6-alpine` | Serves the app; CSP and security headers; login rate limit (5/min); `/api` proxy | Fast, stable line (even minor version = stable). |
| **Caddy** | `caddy:2.11.7-alpine` | The only exposed service: HTTP locally, **automatic Let's Encrypt HTTPS** on a real domain, HSTS | No certificate scripts needed. |
| **PostgreSQL** | `postgres:16.15-alpine` | The production database (`pgdata` volume) | Reliable and free. |
| backup | `postgres:16.15-alpine` + `ops/backup.sh` | Daily `pg_dump`, keeps 14 days, waits for migrations | Has `pg_dump` built in. |
| SQLite | (Python built-in) | Local development and all tests | A single file, zero setup. |

## 10.6 External services

| Service | Plan / cost | Used for | Notes |
|---|---|---|---|
| **Ticketmaster Discovery API v2** | Free key (5,000 calls/day) | Main event source | `locale=*` is required for German venue names. |
| **PredictHQ** | Paid, optional | Predicted attendance | Turns on when `PREDICTHQ_TOKEN` is set. |
| **OpenStreetMap tiles** | Free | Map background | Respect the tile usage policy; heavy use needs a tile provider. |
| **Let's Encrypt** | Free | HTTPS certificates (through Caddy) | Only with a real domain. |
| Slack (incoming webhook) | Free | Sync failure alerts (`ALERT_WEBHOOK_URL`) | Optional. |
| Sentry | Free tier available | Error reporting | Optional. |
| **GitHub + GitHub Actions** | Free for public repositories, minutes included for private ones | Code hosting (`Akhil5Xavier/lime-event-planner`, public) and CI (`.github/workflows/ci.yml`) | CI runs once the repo is pushed. |

## 10.7 Testing and quality tools

| Tool | Version | Role |
|---|---|---|
| **pytest** | 9.1.1 | Backend test runner: 51 tests (chapter 6) |
| FastAPI `TestClient` | (FastAPI 0.162) | In-process API tests |
| `httpx.MockTransport` | (httpx 0.28) | Fake Ticketmaster API |
| SQLite in memory + `StaticPool` | (SQLAlchemy 2.1) | A fresh database per test |
| TypeScript compiler | 5.9.3 | Frontend type check, part of every build |
| GitHub Actions | `actions/checkout@v4`, `setup-python@v5`, `setup-node@v4` | CI: tests, build, Docker smoke test |
| The built-in browser of the Claude desktop app | | Manual browser checks during the build |

## 10.8 Security building blocks

| Concern | How it's handled | Where |
|---|---|---|
| Passwords | bcrypt hashes; never stored or logged in plain text; `set-password` CLI | `security.py`, `cli.py` |
| Sessions | JWT HS256, 8 h expiry, the user is re-checked on every request | `security.py` |
| Secrets | `.env` files (git-ignored); production refuses a weak `JWT_SECRET` or SQLite; API keys scrubbed from errors | `config.py`, `ingest/runner.py` |
| Roles | admin / manager, at router level | `api/*.py` |
| Password guessing | nginx: 5 logins per minute per IP (429) | `frontend/nginx.conf` |
| Injected scripts (XSS) | CSP `script-src 'self'`; React escapes text | `nginx.conf`, frontend |
| Clickjacking etc. | `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS | `nginx.conf`, `Caddyfile` |
| Containers | API runs as a non-root user; only Caddy has published ports | `backend/Dockerfile`, `docker-compose.yml` |
| Data loss | Daily `pg_dump` with 14-day retention; documented restore | `ops/backup.sh`, README |

## 10.9 Where each part of the stack is configured

| File | Configures |
|---|---|
| `backend/requirements.txt` / `requirements.lock` | Python packages (allowed ranges / exact versions) |
| `frontend/package.json` / `package-lock.json` | npm packages (allowed ranges / exact versions) |
| `backend/Dockerfile`, `frontend/Dockerfile` | Images, users, healthchecks |
| `docker-compose.yml` | Services, start-up order, volumes, logs, ports |
| `Caddyfile` | HTTP or HTTPS, HSTS |
| `frontend/nginx.conf`, `proxy_params_lime` | Security headers, rate limits, proxy, caching |
| `.env` (root, for Docker) and `backend/.env` (local) | Secrets and settings; templates in `.env.example` |
| `backend/alembic/` | Database schema history |
| `.github/workflows/ci.yml` | Continuous integration |
| `frontend/vite.config.ts`, `tsconfig.json`, `tailwind.config.js` | Frontend tooling |

## 10.10 Keeping the stack up to date

- **Monthly:**
  - Backend: regenerate `requirements.lock` (instructions at the top of the file) and run `pytest`.
  - Frontend: run `npm outdated`, update within the major version, and run `npm run build`.
- **Base images:** look up current tags on Docker Hub (Python security releases, nginx stable, PostgreSQL 16 minor versions, Caddy) and update the exact tags; never use `latest`.
- **Major upgrades** (React 19, PostgreSQL 17, APScheduler 4, Vite 6+) are their own projects: read the changelog, update on a branch, and run the full checks in chapter 6.

Back to the [guide overview](README.md).
