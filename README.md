# Sandbox Platform

Developer sandbox for **Open Agri Net (OAN)**: a public site with the API catalogue, a
participant portal (sign-up, environment access, try-it console, API history, support) and an
admin console (participants, products and end-points, CMS, masters, queries). Try-it calls are
answered from published samples (mock mode) or routed through the Kong API gateway of the
environment.

## Repository layout

```
sandbox-platform/
├── backend/                 FastAPI + SQLAlchemy 2 + Alembic API (Python 3.12)
│   ├── app/                 controllers → services → repositories → models
│   ├── alembic/             database migrations
│   ├── scripts/             demo catalogue loaders (OpenG2P, A2C), dev helpers
│   ├── tests/               pytest suite (in-memory SQLite)
│   └── .env.example         every backend setting, documented
├── ui/                      Next.js 16 / React 19 web client (public site, portal, console)
│   ├── src/
│   ├── public/
│   ├── Dockerfile           UI image (standalone Next.js server)
│   └── .env.example
├── docker/
│   └── sandbox-api/         API image: Dockerfile + entrypoint (context: repo root)
├── deployment/
│   ├── postgres/initdb/     database snapshot loaded on the first Docker start
│   ├── postgres/empty/      use instead for a clean database
│   └── a2c/                 A2C OpenAPI spec read by the demo catalogue loader
├── .github/workflows/ci.yml backend lint + tests, UI typecheck/lint/build, image builds
├── docker-compose.yml       postgres + api + web (Kong is external)
├── .env.example             settings for docker compose
└── DEPLOYMENT.md            Docker deployment guide
```

## Quick start (Docker)

```bash
cp .env.example .env    # set DB_PASSWORD, JWT keys, GATEWAY_SANDBOX_URL, public URLs
docker compose up -d --build
```

Web: <http://localhost:3005> · API: <http://localhost:8010/oan> (health `/oan/health`).
Full guide, settings and troubleshooting: **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Deployment (DevOps checklist)

What a deployment of this release needs, per environment (dev, staging, production). Every
setting is a variable in `.env` next to `docker-compose.yml`;
[`.env.example`](.env.example) lists them all with local values. `.env` is git-ignored; never
commit secrets. On Kubernetes, put the secrets below in a Secret and the rest in a ConfigMap
with the same names (there is no Helm chart in this repository).

### Before you start

| Item | Detail |
|---|---|
| Host | Docker Engine 24+ with Compose v2. Nothing else on the host. |
| Images | Two images, built from this repo (CI builds them on every push but does not publish them). `api`: `docker build -f docker/sandbox-api/Dockerfile -t <registry>/oan-sandbox-api:<tag> .` (listens on `8000`). `web`: `docker build -t <registry>/oan-sandbox-web:<tag> --build-arg NEXT_PUBLIC_API_BASE_URL=<public API URL> ui` (listens on `3000`). Or `IMAGE_PREFIX=<registry>/oan-sandbox IMAGE_TAG=<tag> docker compose build api web`. |
| One `web` image per environment | The browser API URL (`PUBLIC_API_URL` / `NEXT_PUBLIC_API_BASE_URL`) is built into the `web` image. Build and tag a `web` image per environment; the `api` image is the same everywhere. |
| PostgreSQL | Included in the stack (`postgres:18-alpine`, database `sandbox_db_oan`, volume `oan_pgdata`). For a managed database, remove the `postgres` service and point `DB_HOST` / `DB_PORT` at it (PostgreSQL 18, to match the snapshot). |
| Kong gateway | **Not part of this stack.** The environment's existing Kong must be deployed with the A2C routes and plugins (`jwt`, `key-auth`, `acl`, rate limiting) and be reachable from the `api` container. Its proxy URL is `GATEWAY_SANDBOX_URL`; the stack refuses to start without it. No Redis is needed (only Kong used it). |
| Public host names | One for the web app (e.g. `https://sandbox.<domain>`) and one for the API (e.g. `https://api.<domain>/oan`, or the same host under `/oan`), with TLS on a reverse proxy or load balancer. |
| SMTP | An SMTP account for sign-up codes, password-reset links, invitations and query replies. Without it, codes and links only appear in the API log. |
| Database start mode | **Snapshot** (default): the first start loads `deployment/postgres/initdb` (catalogue, masters, CMS, development accounts). **Clean**: `POSTGRES_INITDB_DIR=./deployment/postgres/empty` + `SEED_ADMIN_PASSWORD` (schema, admin, masters, CMS only). Use clean for production. Either applies only to an **empty** volume. |

### Volumes

| Volume | Mounted at | What | Back up |
|---|---|---|---|
| `oan_pgdata` | `/var/lib/postgresql` (postgres) | Database | Yes (daily `pg_dump`, see DEPLOYMENT.md §6) |
| `oan_uploads` | `/app/uploads` (api) | Participant ID proofs, certificates, product icons and documents | Yes |
| `oan_api_logs` | `/app/logs` (api) | API log files | Ship to the log store |
| `./deployment/a2c` | `/a2c` (api, read-only) | A2C OpenAPI file, read only by `LOAD_DEMO_CATALOGUE` | No (in git) |
| `POSTGRES_INITDB_DIR` | `/docker-entrypoint-initdb.d` (postgres, read-only) | First-start snapshot or empty folder | No (in git) |

### Environment variables

**Required** (the stack does not start without them):

| Variable | Example | Notes |
|---|---|---|
| `DB_PASSWORD` | *(Secret)* | PostgreSQL password. |
| `JWT_ACCESS_TOKEN_KEY`, `JWT_REFRESH_TOKEN_KEY` | *(Secret)* | Two different long random values: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing them logs everyone out. |
| `GATEWAY_SANDBOX_URL` | `https://kong-dev.<domain>` | Proxy URL of the environment's existing Kong. Try-it calls for gateway products (A2C) go here. |

**Per environment** (defaults are for a laptop):

| Variable | Example | Notes |
|---|---|---|
| `PUBLIC_API_URL` | `https://api.<domain>/oan` | API URL users' **browsers** call. Build-time: rebuild `web` after changing it. |
| `ALLOWED_ORIGINS` | `https://sandbox.<domain>` | CORS; the public web URL(s), comma-separated. |
| `PORTAL_URL` | `https://sandbox.<domain>` | Web URL used in email links. |
| `API_INTERNAL_URL` | `http://api:8000/oan` | URL the `web` server uses to reach the API inside the network (public pages). Run time. |
| `APP_ENV` | `sandbox` / `uat` / `production` | `production` also turns off the fixed sign-up code below. |
| `MAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | `true`, …, *(Secret)* | Turn mail on for any shared server. |
| `DEV_FIXED_OTP` | **empty** on shared servers | While mail is off every sign-up code is this value (`000000` by default), so anyone can register any email. Ignored when mail is on or `APP_ENV=production`. |
| `IMAGE_PREFIX`, `IMAGE_TAG` | `<registry>/oan-sandbox`, `1.0.0` | Images to pull/run (`<prefix>-api`, `<prefix>-web`). |

**Clean-database mode only** (first start on an empty volume):

| Variable | Example | Notes |
|---|---|---|
| `POSTGRES_INITDB_DIR` | `./deployment/postgres/empty` | Default `./deployment/postgres/initdb` loads the development snapshot. |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | `admin@<domain>`, *(Secret)* | Master administrator. Seeding is idempotent and runs on every start while the password is set; existing rows are kept. |
| `LOAD_DEMO_CATALOGUE` | `true` / `false` | Adds the A2C products (flagged for the gateway) and the OpenG2P demo product. Re-runnable. |

**Optional** (defaults are fine to start):

| Variable | Default | Notes |
|---|---|---|
| `GATEWAY_ENABLED` | `true` | `false` answers every try-it call from published samples. |
| `GATEWAY_UAT_URL`, `GATEWAY_PROD_URL` | empty | UAT / production gateways when they exist. |
| `API_DEBUG` | `false` | `true` exposes Swagger at `/docs`. Keep `false` on shared servers. |
| `DB_USER`, `DB_NAME` | `postgres`, `sandbox_db_oan` | |
| `API_HOST_PORT`, `WEB_HOST_PORT` | `8010`, `3005` | Host ports the reverse proxy targets. |
| `POSTGRES_HOST_PORT`, `POSTGRES_BIND` | `5433`, `127.0.0.1` | Keep the database on loopback. |
| `DEFAULT_COUNTRY_CODE`, `SITE_NAME` | `ET`, `Open Agri Net` | `SITE_NAME` is build-time for `web`. |
| `LOG_LEVEL` | `INFO` | |

### Reverse proxy

TLS terminates on the proxy: web host → `web` (`WEB_HOST_PORT`), API host or `/oan` path →
`api` (`API_HOST_PORT`). Forward `X-Forwarded-*` headers (the API runs with
`--proxy-headers`). Allow uploads of at least 25 MB on the API route (`MAX_UPLOAD_MB`).
Do not expose PostgreSQL.

### Deploy

```bash
cp .env.example .env        # fill in the variables above
docker compose pull         # or: docker compose build api web
docker compose up -d
docker compose ps           # postgres, api and web all "(healthy)"
```

The `api` container waits for the database, runs `alembic upgrade head`, seeds if
`SEED_ADMIN_PASSWORD` is set, loads the demo catalogue if asked, then starts. No manual
migration step.

### After deploying

1. `GET https://api.<domain>/oan/health` answers `200` with `"database": "up"` and the
   expected `env`.
2. The web app opens on its public URL; the API catalogue lists the products (snapshot: 14
   products; clean + demo catalogue: A2C + OpenG2P).
3. Log in to the admin console. **Snapshot mode: change the passwords of the development
   accounts** (`admin@openagrinet.org`, `participant@openagrinet.org`) at once. Clean mode:
   remove `SEED_ADMIN_PASSWORD` from `.env` after the first start.
4. Sign up a test participant: the code arrives by email (mail on). Approve the participant
   and give it sandbox access in the console.
5. Try-it for a gateway product (A2C) reaches Kong: the API log shows the call to
   `GATEWAY_SANDBOX_URL` and Kong answers (a `401` without credentials still proves the route).
   A connection error means the `api` container cannot reach Kong.
6. Password reset email links point at `PORTAL_URL`.
7. Schedule backups of `oan_pgdata` and `oan_uploads`; ship `oan_api_logs` to the log store.

### Upgrades

Pull (or build) the new images with the new `IMAGE_TAG`, then `docker compose up -d`; the
`api` container applies new migrations on start. Rebuild `web` whenever `PUBLIC_API_URL` or
`SITE_NAME` changes. `docker compose down -v` **deletes all data**; never run it on a shared
server.

## Local development

- **Backend** — see [backend/README.md](backend/README.md):
  `python -m venv venv`, `pip install -r requirements.txt`, copy `.env.example` to `.env`,
  `python -m alembic upgrade head`, `uvicorn app.main:app --reload --port 8010`.
- **UI** — see [ui/README.md](ui/README.md):
  `npm ci`, copy `.env.example` to `.env`, `npm run dev -- -p 3005`.

Checks (the same as CI):

| Part | Command |
| --- | --- |
| Backend lint | `cd backend && ruff check app tests` |
| Backend tests | `cd backend && pytest` |
| UI | `cd ui && npm run typecheck && npm run lint && npm run build` |

## Branches and pull requests

| Branch | Purpose |
| --- | --- |
| `develop` | Integration branch; all work is merged here first |
| `staging` | Release candidate deployed to staging |
| `main` | Released code |

Work happens on a fork. Create a branch from `develop` (or work on the fork's `develop`), push it
to the fork and open a pull request into `Centre-for-Open-Societal-Systems/sandbox-platform`
**`develop`**. `develop` → `staging` → `main` is promoted by pull request.

```bash
git remote add upstream https://github.com/Centre-for-Open-Societal-Systems/sandbox-platform.git
git fetch upstream
git checkout -b feature/<name> upstream/develop
```
