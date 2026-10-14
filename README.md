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
