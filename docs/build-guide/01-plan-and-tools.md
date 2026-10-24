# Chapter 1: Plan and tools

## 1.1 Understand the problem before writing code

The request: Lime's Stuttgart managers want to see all events in Stuttgart on a calendar, so they can place more scooters where demand will spike.

Before touching code, turn that into concrete requirements:

1. **Collect** events automatically. Managers should not have to type them in.
2. **Store** them in a database, so the calendar is fast and history is kept.
3. **Show** them on a calendar. Clicking a day shows that day's events.
4. **Recommend** how many extra scooters to place, where, and when. This is the actual business value; a calendar alone doesn't tell anyone what to do.
5. **Login**, because it's an internal tool.
6. **Map**, because "where" is a location question.

Then answer the decisions that shape everything. Write them down; you'll refer back to them.

| Decision | Choice | Why |
|---|---|---|
| Languages | Python backend, React frontend | Python is strong at calling APIs and processing data. React is the most common UI library, so the code is easy to hand over. |
| Data source | Public APIs, not scraping websites | APIs return structured data and don't break when a website's layout changes. Scrapers do. |
| Which API | Ticketmaster Discovery API (free) as the main source, PredictHQ (paid) as optional | Ticketmaster covers concerts, sport and theatre in Stuttgart and is free. PredictHQ adds *predicted attendance*, which improves the recommendation. Eventbrite was considered but its public search API was shut down. |
| Database | PostgreSQL in production, SQLite for development and tests | Postgres is the reliable standard for multi-user apps. SQLite is a single file, so it needs zero setup while developing. |
| Deployment | Docker Compose on one server | Packages everything so it runs identically anywhere, with one command to start it. |

## 1.2 Architecture

Split the system into a **backend** (data + logic + API) and a **frontend** (what managers see) that talk only through a JSON REST API under `/api/...`.

Why separate them? Each side can be changed, tested and deployed independently. The backend could later serve a mobile app too. The frontend never touches the database directly, so all rules (who may edit what) live in one place: the backend.

Inside the backend, keep layers separate:

```
api/        HTTP layer: parse request, check login, call services, return JSON
services/   business logic: "which events today", "how many scooters"
ingest/     talking to outside APIs and saving what they return
models.py   database tables
```

Rule of thumb: **API code should be thin.** If you can't test a piece of logic without making an HTTP request, it's in the wrong layer.

## 1.3 Install the tools

You need:

| Tool | Version used | Why |
|---|---|---|
| Python | 3.12+ (3.15 locally, 3.12 in Docker) | Runs the backend. |
| Node.js | 24 LTS | Runs the frontend build tools (Vite, TypeScript). Use an LTS ("long-term support") version; Node 20 reached end-of-life in April 2026. |
| Git | any recent | Version control. |
| Docker Desktop | any recent | Only needed to run the production setup locally. |
| A code editor | VS Code recommended | |

On Windows, install with winget from PowerShell. Each one shows a Windows admin (UAC) prompt; approve it.

```powershell
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Git.Git -e
winget install --id Docker.DockerDesktop -e
```

**Close and reopen your terminal afterwards.** Programs read PATH when they start, so an already-open terminal won't find `node` or `git`. This caught us during the original build: Node and Git were installed but "not recognized" until the terminal was restarted.

Check:

```powershell
python --version
node --version
npm --version
git --version
```

## 1.4 Create the project

```powershell
mkdir D:\Projects\Lime
cd D:\Projects\Lime
mkdir backend, frontend, docs
git init -b main
```

`git init -b main` creates the repository with `main` as the branch name.

Set your git identity. Use `--global` if you want it for all projects, or leave it off to set it for this repository only:

```powershell
git config user.name "Your Name"
git config user.email "you@example.com"
```

### `.gitignore`

Create `.gitignore` in the project root **before your first commit**. It lists things git must never store:

```gitignore
.env              # secrets (API keys, passwords)
*.db              # local SQLite databases
__pycache__/      # Python bytecode caches
.pytest_cache/
.venv/            # Python virtual environment (huge, machine-specific)
node_modules/     # npm packages (huge, re-installable)
dist/             # frontend build output
backups/          # database dumps
.claude/          # local tooling with machine-specific paths
```

Why each matters: `.env` holds secrets, and once a secret is in git history it is effectively public, even if you delete it later. Build outputs and installed packages are large and can always be regenerated from `requirements.txt` and `package.json`.

### `.gitattributes`

```gitattributes
*.sh text eol=lf
Caddyfile text eol=lf
frontend/nginx.conf text eol=lf
frontend/proxy_params_lime text eol=lf
```

Windows uses CRLF line endings; Linux uses LF. These files run inside Linux containers, and a shell script with CRLF endings fails with confusing errors like `/bin/sh^M: bad interpreter`. This file forces LF for them even on a Windows checkout.

## 1.5 Create the Python environment

```powershell
cd D:\Projects\Lime\backend
python -m venv .venv
```

A **virtual environment** (`.venv`) is a private copy of Python just for this project. Packages you install go there, not into your system Python, so projects can't conflict with each other.

You don't need to "activate" it. Call its Python directly, which always works in PowerShell and avoids execution-policy errors:

```powershell
.venv\Scripts\python.exe -m pip install --upgrade pip
```

(macOS/Linux: `.venv/bin/python`.)

### `requirements.txt`: what the backend needs and why

```text
fastapi>=0.115           # web framework for the REST API
uvicorn>=0.30            # the server process that runs FastAPI
sqlalchemy>=2.0          # talks to the database using Python classes
alembic>=1.13            # database migrations (schema changes over time)
pydantic-settings>=2.4   # reads settings from environment variables / .env
email-validator>=2.2     # validates email addresses in user forms
httpx>=0.27              # HTTP client to call Ticketmaster/PredictHQ
apscheduler>=3.10,<4     # runs the nightly sync on a schedule
pyjwt>=2.9               # creates and checks login tokens
bcrypt>=4.2              # hashes passwords
psycopg[binary]>=3.2     # PostgreSQL driver
tzdata>=2024.1           # timezone database (Windows has none built in)
sentry-sdk>=2.0          # optional error reporting
```

`>=` means "this version or newer". That's flexible for development, but a production build should be exactly repeatable, so in chapter 8 you'll generate a `requirements.lock` file with exact versions.

**Why `apscheduler<4`?** Version 4 is a complete rewrite with a different API. The cap protects you from a surprise breaking upgrade.

**Why `tzdata`?** The code uses `zoneinfo.ZoneInfo("Europe/Berlin")`. Linux has a timezone database built in; Windows doesn't, so Python needs this package.

`requirements-dev.txt` adds tools only developers need:

```text
-r requirements.txt
pytest>=8.3
```

Install:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> **Pitfall found during the build:** `uvicorn[standard]` pulls in PyYAML, which had no prebuilt package for brand-new Python 3.15 and tried to compile from source (needing Microsoft C++ Build Tools). Plain `uvicorn` doesn't need it. If an install fails with "Microsoft Visual C++ 14.0 or greater is required", a package has no wheel for your Python version. Use a slightly older Python, or drop the optional extra.

Create the empty package folders. Python treats a folder as an importable package when it contains `__init__.py`:

```powershell
mkdir app, app\api, app\ingest, app\services, app\seed, tests
ni app\__init__.py, app\api\__init__.py, app\ingest\__init__.py, app\services\__init__.py, app\seed\__init__.py, tests\__init__.py
```

## Checkpoint

- `python --version`, `node --version` and `git --version` all work in a new terminal.
- `backend\.venv` exists, and `.venv\Scripts\python.exe -c "import fastapi, sqlalchemy; print('ok')"` prints `ok`.
- `git status` shows only `.gitignore` and `.gitattributes` as untracked; the `.venv` folder is ignored.

Next: [Chapter 2, Backend foundation](02-backend-foundation.md).
