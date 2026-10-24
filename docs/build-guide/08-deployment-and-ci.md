# Chapter 8: Deployment and CI

This chapter packages everything so it runs safely on a server with one command, and sets up automatic checks on every push.

## The production stack

```
Internet ──► caddy :443 (HTTPS) ──► frontend: nginx :80 ──► /api ──► backend: FastAPI :8000 ──► db: Postgres
                                         └─ static React files          worker: nightly sync ────┘
                                                                         backup: daily pg_dump ───┘
```
Only Caddy is reachable from outside. Everything else talks over Docker's private network, using service names (`db`, `backend`) as host names.

---

## 8.1 Pinning versions

**Why:** "it worked last week" problems usually come from something updating underneath you. Pin everything so a rebuild gives the same result.

### `backend/requirements.lock`
`requirements.txt` says *what* you need (`fastapi>=0.115`); the lock file says *exactly which versions* (`fastapi==0.162.0`) of everything, including dependencies of dependencies. Generate it in a **clean** environment, so test tools don't end up in it:
```powershell
python -m venv $env:TEMP\lockenv
& $env:TEMP\lockenv\Scripts\python.exe -m pip install -r requirements.txt
& $env:TEMP\lockenv\Scripts\python.exe -m pip freeze --exclude pip > requirements.lock
```
On Windows, remove the `colorama` line it adds, which only Windows needs. Add a header comment explaining how to regenerate the file.

### Image tags
Use exact tags such as `python:3.12.15-slim`, `node:24.20.0-alpine`, `nginx:1.30.6-alpine`, `postgres:16.15-alpine` and `caddy:2.11.7-alpine`, never `latest`. **Look up real tags** on Docker Hub (hub.docker.com → the image → Tags). A guessed tag fails the build. Prefer LTS or stable lines: an even-numbered nginx minor version (1.30) is the stable line, and Node 24 is LTS.

---

## 8.2 `backend/Dockerfile`

```dockerfile
FROM python:3.12.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["sh", "-c", "python -m app.cli init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
```
Line by line:
- `slim`: a small Debian image; it has what Python packages need.
- `PYTHONDONTWRITEBYTECODE` stops `.pyc` files being written; `PYTHONUNBUFFERED` makes logs appear immediately instead of being buffered.
- **The lock file is copied before the code.** Docker caches each step, so dependencies are only re-installed when the lock file changes, not on every code edit. Builds go from minutes to seconds.
- **The non-root user** (`useradd`, `USER app`) means that if someone ever exploited the app, they wouldn't be root inside the container.
- `HEALTHCHECK` lets Docker know whether the app is actually working, not just running. It uses Python's built-in `urllib` because `slim` has no curl.
- `CMD` first runs the migrations and venue seed, then **`exec`** replaces the shell with uvicorn, so it receives the stop signal directly and shuts down cleanly.
- `--host 0.0.0.0` accepts connections from other containers, not only from inside this one.
- `--proxy-headers` and `--forwarded-allow-ips='*'` trust `X-Forwarded-*` headers from nginx, so the real client IP and scheme are known. That's safe because the backend is only reachable from inside the private network.

### `backend/.dockerignore`
`.venv`, `__pycache__`, `.pytest_cache`, `*.db`, `.env` and `tests`. These are kept out of the image: smaller, faster, and **no secrets or local databases baked in**.

---

## 8.3 `frontend/Dockerfile`: a multi-stage build

```dockerfile
FROM node:24.20.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_SENTRY_DSN=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
RUN npm run build

FROM nginx:1.30.6-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY proxy_params_lime /etc/nginx/proxy_params_lime
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK ... CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
```
**Two stages:** the first has Node and builds the app; the second only has nginx and the built files. The final image doesn't contain Node or `node_modules`, so it's small and has fewer things to attack.

- `npm ci` installs exactly the lock file's versions and fails if `package.json` and the lock file disagree.
- `VITE_*` variables are compiled into the JavaScript **at build time**, which is why the Sentry DSN is a build argument, not a runtime setting.

---

## 8.4 `frontend/nginx.conf`

```nginx
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
```
A rate-limit zone: 5 requests per minute per IP, with 10 MB of memory to track IPs. It's used only for the login endpoint, to stop password guessing.

Inside `server { ... }`:
- **`set_real_ip_from`** (private ranges) and **`real_ip_header X-Forwarded-For`**: requests arrive through Caddy, so without this nginx would see Caddy's IP for everyone, and the rate limit would block *all* users after 5 logins. Only private network addresses are trusted to set the real IP.
- `gzip` compresses CSS, JS and JSON.
- **Security headers:**
  | Header | Protects against |
  |---|---|
  | `Content-Security-Policy` | Injected scripts (XSS). Only scripts from this site may run. Images may come only from this site and OpenStreetMap tiles; connections only to this site and Sentry. `'unsafe-inline'` is allowed for **styles only**, because FullCalendar and Leaflet set inline styles. |
  | `X-Frame-Options: DENY` | The site being embedded in another page to trick clicks ("clickjacking"). |
  | `X-Content-Type-Options: nosniff` | The browser guessing file types. |
  | `Referrer-Policy` | Leaking full URLs to other sites. |
  | `Permissions-Policy` | The page using the camera, microphone or location. |
- **The `add_header` trap:** in nginx, a `location` block with its own `add_header` **drops all headers set at server level**. So the headers are only set at server level, and the cache rule uses `expires` instead of `add_header Cache-Control`.
- `location = /api/auth/login`: `limit_req zone=login burst=5 nodelay` allows a short burst, then refuses; `limit_req_status 429` returns "Too Many Requests" (the default would be a misleading 503).
- `location /api/`: proxies to `http://backend:8000`, with headers from `proxy_params_lime`.
- `location /assets/`: `expires 1y`. Built file names contain a content hash, so a changed file gets a new name and caching forever is safe.
- `location /`: `try_files $uri /index.html`, the **SPA fallback**. `/day/2026-11-07` isn't a real file, so nginx serves `index.html` and React Router shows the right page. `expires -1` stops `index.html` itself being cached, so users get new asset names right after a deploy.

### `frontend/proxy_params_lime`
The shared proxy headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`) and a 60 s timeout, in one file included by both API locations.

---

## 8.5 `Caddyfile`: automatic HTTPS

```
{$DOMAIN} {
	encode zstd gzip
	header Strict-Transport-Security "max-age=31536000; includeSubDomains"
	reverse_proxy frontend:80
}
```
**Why Caddy?** It gets and renews free Let's Encrypt certificates **automatically**, with no certbot or cron jobs. That needs DNS for `DOMAIN` pointing at the server and ports 80 and 443 open. With `DOMAIN=localhost` it uses its own local certificate for testing.

`Strict-Transport-Security` (HSTS) tells browsers to always use HTTPS for this site for a year.

---

## 8.6 `ops/backup.sh` and `ops/backup-loop.sh`

`backup.sh`:
1. `set -eu`: stop on any error or undefined variable.
2. `pg_dump --no-owner --clean --if-exists | gzip > file.partial`. `--clean --if-exists` makes the dump drop and recreate tables, so restoring into an existing database works.
3. **Write to `.partial`, then rename** only on success. A failed or half-written dump never looks like a valid backup.
4. Delete backups older than `BACKUP_KEEP_DAYS`.

`backup-loop.sh` runs a backup at start-up and then every 24 hours.

**Why a loop and not cron?** Cron jobs inside a container **don't get the container's environment variables**, so `PGPASSWORD` wouldn't be set and every backup would fail silently. The loop inherits the environment.

---

## 8.7 `docker-compose.yml`

### Reusable blocks
```yaml
x-logging: &logging
  driver: json-file
  options: { max-size: "10m", max-file: "5" }

x-backend-env: &backend-env
  ENVIRONMENT: production
  LOG_FORMAT: json
  DATABASE_URL: postgresql+psycopg://lime:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}@db:5432/lime
```
- `x-...` blocks are reusable snippets: `&name` defines one and `*name` (or `<<: *name` to merge) uses it.
- **Log rotation:** without it, Docker logs grow until the disk is full, a classic way servers die after a few months.
- **`${VAR:?message}`** stops with that message if the variable is missing, instead of starting with an empty password.

### Services
| Service | Key settings and why |
|---|---|
| `db` | `pgdata` volume, so data survives container rebuilds. Healthcheck `pg_isready`. **No published ports**: only reachable inside Docker. |
| `backend` | Built from `./backend`. `env_file: .env` for secrets. `SCHEDULER_ENABLED: "false"`, because the worker schedules. `depends_on: db: condition: service_healthy` means it only starts once Postgres accepts connections. |
| `worker` | **The same image** with `command: python -m app.cli scheduler`. Waits for `backend` to be healthy, which means migrations have run. `healthcheck: disable: true`, because it inherits the backend's HTTP healthcheck, and the worker has no web server, so it would always be "unhealthy". |
| `frontend` | Passes `VITE_SENTRY_DSN` as a build argument. Waits for `backend` to be healthy, because nginx refuses to start if the `backend` host name in `proxy_pass` can't be resolved yet. |
| `caddy` | **The only service with `ports`** (80 and 443). `caddy_data` stores certificates, so they survive restarts and you don't hit Let's Encrypt's rate limits. |
| `backup` | The `postgres` image (it has `pg_dump`). Mounts `./ops` read-only and `./backups` for output. |

`restart: unless-stopped` on everything: containers come back after a crash or server reboot.

### `.env.example`
A template listing every variable with a comment, without real values. Copy it to `.env` and fill it in. It's committed, so new team members know what to set; `.env` itself never is.

---

## 8.8 `.github/workflows/ci.yml`: automatic checks

Runs on every push and pull request. Three jobs:

1. **`backend`:** Python 3.12, `pip install -r requirements.lock pytest`, `pytest -q`, then `init-db` on an empty SQLite database, which proves the migrations apply from scratch. `cache: pip` keyed on the lock file makes reruns fast.
2. **`frontend`:** Node 24, `npm ci`, `npm run build` (typecheck plus build).
3. **`docker`** (only if both pass, `needs: [backend, frontend]`):
   - create a `.env` with a random `JWT_SECRET` (**before** building, because `env_file: .env` must exist);
   - `docker compose build`;
   - `docker compose up -d --wait --wait-timeout 180`, which waits until every healthcheck passes;
   - smoke tests through Caddy over HTTPS: `curl -fsSk https://localhost/api/health` (`-k` accepts Caddy's local certificate) and a check that the page contains `<div id="root">`;
   - `docker compose logs` on failure, so you can see why.

---

## 8.9 Deploying for real

1. A Linux VM (2 vCPU, 4 GB RAM, 40 GB disk) with Docker; only ports 80 and 443 open; ideally only reachable through the company VPN.
2. DNS: point `events.yourdomain` at the server.
3. On the server:
   ```bash
   git clone <repo> && cd <repo>
   cp .env.example .env    # set DOMAIN, JWT_SECRET, POSTGRES_PASSWORD, TICKETMASTER_API_KEY, ALERT_WEBHOOK_URL
   docker compose up -d --build --wait
   docker compose exec backend python -m app.cli create-user you@company.com --role admin
   ```
4. Open `https://<domain>`, go to **Admin**, click **Sync now**, and add the managers.
5. Point an uptime monitor at `/api/health` and `/api/health/ingest`. Copy `./backups` off the server, for example nightly to S3. Test a restore (the README has the commands).

Updating: `git pull && docker compose up -d --build --wait`. Migrations run automatically on start.

## Checkpoint

With Docker Desktop installed, set `DOMAIN=localhost` in `.env`, run `docker compose up -d --build --wait`, and open <https://localhost>. Then check:
- `docker compose ps` shows every service healthy or running;
- `docker compose exec backend id` shows `uid=10001(app)`;
- a 6th wrong login within a minute returns 429;
- `docker compose exec backup /ops/backup.sh` writes a file into `backups/`.

Next: [Chapter 9, Verification and lessons](09-verification-and-lessons.md).
