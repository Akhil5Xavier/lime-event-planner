# Build guide: Lime Stuttgart Event Planner from scratch

This guide walks you through building this project yourself, step by step, in the order it was originally built. For every file it explains **what it is for**, **what each function does**, and **why it was done that way**. It also lists the mistakes that were made along the way and how they were found.

The finished code is in this repository. Use it as your answer key: write each file yourself following the chapter, then compare it with the real file.

## How to use this guide

- Work through the chapters **in order**. Each one builds on the previous one.
- Every chapter ends with a **checkpoint**: something you run to prove that part works before moving on. Don't skip them; finding a bug in chapter 3 is much easier than finding it in chapter 8.
- Code blocks show the important parts of each file. Where a file is long, the guide shows the key pieces and explains the rest, and you can look at the full file in the repo.
- Commands are for **Windows PowerShell**, because that's what this was built on. Differences for macOS/Linux are noted where they matter.

## Chapters

| # | Chapter | You will build |
|---|---------|----------------|
| 1 | [Plan and tools](01-plan-and-tools.md) | The plan, the architecture, the installed tools, the empty project |
| 2 | [Backend foundation](02-backend-foundation.md) | Settings, database connection, tables, passwords and login tokens, seed venues |
| 3 | [Data collection](03-data-collection.md) | Ticketmaster and PredictHQ connectors, venue matching, duplicate detection, sync runner, alerts |
| 4 | [Recommendation logic](04-recommendation-logic.md) | "Which events run on this day", the scooter formula, hotspots, cleanup |
| 5 | [API, CLI and migrations](05-api-cli-migrations.md) | Request/response schemas, every endpoint, the app entry point, scheduler, CLI, Alembic |
| 6 | [Testing](06-backend-tests.md) | All 51 backend tests and why each exists, frontend checks, live checks, CI, known gaps |
| 7 | [Frontend](07-frontend.md) | The React app: API client, login, calendar, day view, map, forms, admin |
| 8 | [Deployment and CI](08-deployment-and-ci.md) | Dockerfiles, nginx, Caddy, Compose, backups, GitHub Actions |
| 9 | [Verification and lessons](09-verification-and-lessons.md) | How everything was tested end to end, and every bug found along the way |
| 10 | [Software stack](10-software-stack.md) | Every tool, library, image and service with its exact version and why it's used |

## The project in one picture

```
 Data sources                Backend (Python)                       Frontend (React)
┌──────────────┐     ┌────────────────────────────────┐      ┌──────────────────────┐
│ Ticketmaster │──┐  │ worker: nightly sync 03:00     │      │ Login                │
│ PredictHQ    │──┼─►│  → match venues, find dupes    │      │ Calendar (month/week)│
│ Manual entry │──┘  │ PostgreSQL database            │◄────►│ Day view + map       │
└──────────────┘     │ FastAPI REST API (JWT login)   │ JSON │ Venues, Admin        │
                     │ Recommendation engine          │      └──────────────────────┘
                     └────────────────────────────────┘
                        ▲ Caddy (HTTPS) → nginx → /api
```

## Final folder layout

```
Lime/
├── .env.example            template for secrets and settings
├── .gitignore / .gitattributes
├── Caddyfile               HTTPS entry point config
├── docker-compose.yml      runs all services together
├── README.md               how to run and operate it
├── .github/workflows/ci.yml
├── ops/                    backup scripts
├── docs/build-guide/       this guide
├── backend/
│   ├── requirements.txt / requirements.lock / requirements-dev.txt
│   ├── Dockerfile, .dockerignore
│   ├── alembic.ini, alembic/ (env.py, script.py.mako, versions/0001, 0002, 0003)
│   ├── app/
│   │   ├── config.py, db.py, models.py, schemas.py, security.py, geo.py
│   │   ├── observability.py, alerts.py, scheduler.py, cli.py, main.py
│   │   ├── seed/venues.py
│   │   ├── ingest/ (base, ticketmaster, predicthq, store, runner)
│   │   ├── services/ (events, planning, deployment, cleanup)
│   │   └── api/ (auth, users, venues, events, ingest, health)
│   └── tests/ (conftest, test_ingest, test_venue_matching, test_deployment, test_api,
│               test_production, test_cli, fixtures/)
└── frontend/
    ├── package.json, tsconfig.json, vite.config.ts, tailwind/postcss config, index.html
    ├── Dockerfile, nginx.conf, proxy_params_lime
    └── src/
        ├── main.tsx, App.tsx, index.css
        ├── api/ (client.ts, hooks.ts, types.ts)
        ├── auth/AuthContext.tsx
        ├── lib/ (format.ts, useCategoryParam.ts)
        ├── components/ (Layout, CategoryFilter, EventCard, DayMap, EventForm)
        └── pages/ (LoginPage, CalendarPage, DayPage, VenuesPage, AdminPage)
```
