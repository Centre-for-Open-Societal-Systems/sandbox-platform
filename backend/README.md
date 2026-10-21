# OAN Sandbox Backend

Developer sandbox API for **Open Agri Net (OAN)** — a shared agricultural data
network. Ethiopia is the first member country; the schema and services are
multi-country from the ground up.

Built with FastAPI, SQLAlchemy 2.0 and PostgreSQL.

## Architecture

Requests flow strictly downward through the layers; nothing skips one.

```
controllers/   HTTP routing, auth guards, response envelopes
   ↓
services/      business rules, orchestration, audit and notification calls
   ↓
repositories/  persistence only — queries and writes, no business rules
   ↓
models/        SQLAlchemy tables
```

Supporting packages:

| Package | Responsibility |
| --- | --- |
| `core/` | database engine, security, dependencies, pagination, permissions, error handling |
| `schemas/` | Pydantic request and response models |
| `utils/` | validators, file storage, OpenAPI/curl tooling, spreadsheet exports |
| `seeds/` | idempotent reference data for a fresh install |

### Response envelope

Every endpoint returns the same shape, so clients need no per-route handling:

```json
{ "message": "Products loaded.", "status": true, "code": 200, "data": { } }
```

Serialisation happens inside `core/responses.py`, so controllers hand it plain
Python objects and Pydantic models.

### Authentication

Two independent audiences, each with its own guard:

- **Admins** — back-office console, permission-checked per screen
- **Participants** — the organisations and developers consuming the APIs

Both present two headers. The JWT proves identity; the auth key resolves a
server-side session row, so signing out invalidates access immediately rather
than waiting for the token to expire.

```
x-access-token: <jwt>
x-auth-key:     <session handle returned by login>
```

### Multi-country model

The reference Indian system hard-coded one national hierarchy. OAN uses a
generic four-level tree in `admin_area`, and each country names its own tiers
through `country.level_labels`:

| Level | Ethiopia | Kenya |
| --- | --- | --- |
| 1 | Region | County |
| 2 | Zone | Sub-county |
| 3 | Woreda | Ward |
| 4 | Kebele | Village |

Field formats that vary by country (mobile numbers, tax ids, registration
numbers, postal codes) are resolved through `utils/validators.COUNTRY_RULES`.
Onboarding a country means adding an entry there and seeding its areas — not
editing call sites.

## Getting started

```bash
python -m venv venv
venv\Scripts\activate            # PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env           # then fill in the secrets
python -m alembic upgrade head
set SEED_ADMIN_PASSWORD=<choose one>
python -m app.seeds.seed

uvicorn app.main:app --reload --port 8010   # 8000 is used by another container here
```

The API is then at <http://localhost:8010/oan>, with interactive docs at
<http://localhost:8010/docs> while `DEBUG=true`. `ALLOWED_ORIGINS` in `.env` must
list the web client's origin (`http://localhost:3005` locally).

### Required configuration

`JWT_ACCESS_TOKEN_KEY` and `JWT_REFRESH_TOKEN_KEY` have development defaults
that **must** be replaced before any deployment:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Common tasks

| Task | Command |
| --- | --- |
| Run the tests | `python -m pytest` |
| Lint | `python -m ruff check app tests` |
| Format | `python -m ruff format app tests` |
| New migration | `python -m alembic revision --autogenerate -m "..."` |
| Apply migrations | `python -m alembic upgrade head` |
| Re-seed reference data | `python -m app.seeds.seed` |

Seeding is idempotent — it only fills gaps, so it is safe to re-run after
adding new reference data.

## Adding a console screen

1. Add a member to `core/permissions.Permission` and an entry in
   `PERMISSION_TREE`. Ids are append-only — renumbering silently repoints
   existing role grants.
2. Guard the route with `Depends(require_permission(Permission.YOUR_SCREEN))`.

The catalogue is synchronised into `adm_permission` at startup, so no data
migration is needed.

## Docker

The whole stack (PostgreSQL, API, web) runs from the repository's
`docker-compose.yml`; see `../DEPLOYMENT.md`. The API image is built from
`../docker/sandbox-api/Dockerfile` (context: repository root); its entrypoint
(`docker/sandbox-api/docker-entrypoint.sh`) waits for the database, runs
`alembic upgrade head`, seeds when `SEED_ADMIN_PASSWORD` is set and loads the demo
catalogue when `LOAD_DEMO_CATALOGUE=true`.

## Sandbox console (try-it)

`POST /oan/participant/try-it` runs one catalogue end-point for the signed-in
participant (`services/sandbox_service.py`).

- **Upstream:** the base URL is the end-point's `sandbox_api_url`, `uat_api_url`
  or `prod_api_url`, falling back to `GATEWAY_BASE_URL`.
- **Mock mode:** in SANDBOX with no upstream configured, the call is answered
  from the stored response samples (`endpoint_schema`) instead. This mirrors
  the reference `Sandbox_play_api`:
  - Missing required header or path parameters get the 401 sample.
  - A body that equals a sample's `req_json` gets that sample's response.
  - Anything else gets the 200 sample.
  - Mock responses carry `x-sandbox-mock: true`.
  - Every call, mocked or real, is written to `api_log`.
- **Participant API history:**
  - `POST /oan/participant/api-history` accepts the same filters as the admin
    history: environment, method, status_code, product_id, endpoint_id,
    date_from, date_to, search.
  - `GET /oan/participant/api-history/{id}` returns the full request and response.
  - Both are always restricted to the caller's own calls.

Endpoints and samples are created from an OpenAPI document with
`POST /oan/admin/products/import-spec`, or edited in the console's Product
Details and Proxy Info screens. The importer:
- resolves `$ref`s;
- samples the first non-null `anyOf`/`oneOf` alternative;
- uses schema defaults.

## APISIX gateway — admin integration planned, not built

All OAN data APIs are published through the Apache APISIX gateway. Try-it already routes
gateway products through its proxy (`GATEWAY_ENABLED`, `GATEWAY_*_URL`, in
`services/sandbox_service.py`); nothing gateway-specific is used there. **The Admin API
integration is not implemented yet:** `GATEWAY_ADMIN_TOKEN` is read nowhere.

| Part | Plan |
| --- | --- |
| Clients | `app/integrations/apisix/`: an Admin API client (consumers, `key-auth` / `jwt-auth` credentials, consumer groups for `consumer-restriction`, `limit-count`, routes listing) and a pooled proxy client |
| Data | `gateway_consumer` and `gateway_credential` tables, one per participant and environment, with secrets encrypted |
| Lifecycle | Provision on SANDBOX/UAT/PROD approval; revoke on reject, disable or delete |
| Try-it | Calls go through the APISIX proxy with the participant's credential injected server-side; `apikey` is redacted in logs |
| Catalogue | A "Sync from APISIX" import of routes |
| History | A `POST /oan/gateway/apisix/logs` receiver for APISIX's `http-logger` plugin, so API history shows real traffic |
| Settings | Admin API URL and key per environment |

The open questions (auth plugin, per-environment gateways, Admin URL/key) are listed in the
root README under *Project status*.
## Integration seams

These are deliberately isolated so a member country can plug in its own
infrastructure:

| Seam | Location | Default |
| --- | --- | --- |
| Object storage | `utils/files.py` | local disk; GCS and S3 branches provided |
| Email | `services/notification_service.py` | SMTP, disabled unless configured |
| SMS / OTP delivery | `services/notification_service.send_sms` | logs only — wire the national aggregator |
| API gateway | `services/sandbox_service.py` + `GATEWAY_*` settings | direct upstream call |

## Not included

The consent-manager (ACM) module from the reference system is deliberately out
of scope for this build.
