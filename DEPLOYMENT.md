# OAN Sandbox — Docker deployment

The sandbox runs from one Compose file, `docker-compose.yml` in this folder. Nothing has to be
installed on the host except Docker Engine 24+ with Compose v2.

```
browser ──> web (Next.js)  :3005 ──> api (FastAPI) :8010 ──> postgres :5432 (inside the network)
                                         │
                                         └──> existing APISIX gateway  (GATEWAY_SANDBOX_URL)
```

| Service | Image | Host port (default) | Purpose |
| --- | --- | --- | --- |
| `web` | built from `ui/Dockerfile` | `3005` | Public site, participant portal, admin console |
| `api` | built from `docker/sandbox-api/Dockerfile` (context: repo root) | `8010` | Sandbox API (`/oan/...`, health `/oan/health`) |
| `postgres` | `postgres:18-alpine` | `127.0.0.1:5433` | Database `sandbox_db_oan` |

**The API gateway is not part of this stack.** The API calls the Apache APISIX gateway already
deployed for the environment (dev, staging and so on) at `GATEWAY_SANDBOX_URL`. The stack will
not start until that URL is set. Redis is not included either: the API does not use it (only
the gateway's rate limiting does).

## 1. First start

```bash
cd sandbox-platform
cp .env.example .env
#   set DB_PASSWORD, JWT_ACCESS_TOKEN_KEY, JWT_REFRESH_TOKEN_KEY
#   (python -c "import secrets; print(secrets.token_urlsafe(48))")
#   set PUBLIC_API_URL / ALLOWED_ORIGINS / PORTAL_URL to the public addresses
#   set GATEWAY_SANDBOX_URL to the existing APISIX proxy URL of this environment
docker compose up -d --build
docker compose ps          # postgres, api and web all "(healthy)"
```

Open `http://<host>:3005`. API health: `http://<host>:8010/oan/health`.

On the **first start** (empty `oan_pgdata` volume) PostgreSQL loads
`deployment/postgres/initdb/01-oan-sandbox-data.sql.gz`, then runs `02-use-deployed-gateway.sql`.
The snapshot is a copy of the development database
taken on 13 Oct 2026 with the full schema, the API catalogue (14 products, 194 end-points with
samples), masters, geography, CMS pages, FAQs, terms, email templates, roles, the admin account
and two test participant accounts. Login sessions and activity logs were left out.

Then the `api` container:
1. waits for PostgreSQL,
2. runs `alembic upgrade head` (applies any migration newer than the snapshot),
3. seeds reference data if `SEED_ADMIN_PASSWORD` is set (idempotent; existing rows are kept),
4. loads the demo catalogue if `LOAD_DEMO_CATALOGUE=true` (re-runnable, no duplicates),
5. starts the server.

Later restarts skip the init dump; the data stays in the `oan_pgdata` volume.

> **Accounts in the snapshot** are development accounts (admin `admin@openagrinet.org`,
> participant `participant@openagrinet.org`). Change their passwords after the first start,
> or use the clean-database mode below for anything beyond a test server.

## 2. Start from a clean database (no copied data)

In `.env`:

```
POSTGRES_INITDB_DIR=./deployment/postgres/empty
SEED_ADMIN_EMAIL=admin@your-domain
SEED_ADMIN_PASSWORD=<strong password>
LOAD_DEMO_CATALOGUE=true      # optional: A2C (11 products) + OpenG2P demo product
```

Then `docker compose up -d --build`. The API creates the schema, the master administrator,
countries, Ethiopian regions and zones, lookup tables, categories, email templates and CMS
content. This only applies to an **empty** volume. To switch an existing installation, remove
the volume first (this deletes the data): `docker compose down -v`.

## 3. Configuration (`.env`)

| Variable | Default | Notes |
| --- | --- | --- |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME` | `postgres`, —, `sandbox_db_oan` | `DB_PASSWORD` is required |
| `JWT_ACCESS_TOKEN_KEY`, `JWT_REFRESH_TOKEN_KEY` | — | Required; long random values |
| `PUBLIC_API_URL` | `http://localhost:8010/oan` | URL **browsers** use for the API. Built into the web image: run `docker compose build web` after changing it |
| `API_INTERNAL_URL` | `http://api:8000/oan` | URL the **web server** uses to fetch the public pages (catalogue, FAQs, terms, home) over the Docker network. Read at run time |
| `ALLOWED_ORIGINS` | `http://localhost:3005` | CORS; the public web URL(s), comma-separated |
| `PORTAL_URL` | `http://localhost:3005` | Web URL used in email links (password reset, invitations) |
| `API_HOST_PORT`, `WEB_HOST_PORT` | `8010`, `3005` | Host ports |
| `POSTGRES_HOST_PORT`, `POSTGRES_BIND` | `5433`, `127.0.0.1` | DB port on the host; loopback only by default |
| `API_DEBUG` | `false` | `true` exposes Swagger at `/docs` |
| `MAIL_ENABLED`, `SMTP_*` | off | Needed for sign-up codes, reset links and query replies to be emailed |
| `GATEWAY_SANDBOX_URL` | — (required) | Proxy URL of the **existing** APISIX for this environment; try-it calls for gateway products go here |
| `GATEWAY_ENABLED` | `true` | Route products flagged "Served through the API gateway" via APISIX |
| `GATEWAY_UAT_URL`, `GATEWAY_PROD_URL` | empty | External UAT/production gateways when they exist |
| `POSTGRES_INITDB_DIR` | `./deployment/postgres/initdb` | `./deployment/postgres/empty` for a clean database |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `LOAD_DEMO_CATALOGUE` | —, —, `false` | Clean-database mode |
| `IMAGE_PREFIX`, `IMAGE_TAG` | `oan-sandbox`, `latest` | Names of the built images (`oan-sandbox-api`, `oan-sandbox-web`) |

## 4. Behind a domain / reverse proxy

Put a TLS reverse proxy (nginx, Traefik, a cloud load balancer) in front of `web` (3005) and
`api` (8010), for example `https://sandbox.example.org` → web and
`https://sandbox.example.org/oan` or `https://api.example.org/oan` → api. Then set:

```
PUBLIC_API_URL=https://api.example.org/oan
ALLOWED_ORIGINS=https://sandbox.example.org
PORTAL_URL=https://sandbox.example.org
```

and rebuild the web image: `docker compose up -d --build web`.
The API trusts `X-Forwarded-*` headers from the proxy (`--proxy-headers`).

## 5. Building and pushing images (CI/CD)

```bash
IMAGE_PREFIX=registry.example.org/oan IMAGE_TAG=1.0.0 docker compose build api web
docker push registry.example.org/oan-api:1.0.0
docker push registry.example.org/oan-web:1.0.0
```

The web image is tied to its `PUBLIC_API_URL`; build one per environment.
On the server, set the same `IMAGE_PREFIX`/`IMAGE_TAG` and run `docker compose pull && docker compose up -d`.

## 6. Operations

```bash
docker compose logs -f api                      # API log (also in the oan_api_logs volume)
docker compose exec api python -m alembic current
docker compose exec postgres psql -U postgres -d sandbox_db_oan

# backup / restore
docker compose exec -T postgres pg_dump -U postgres -d sandbox_db_oan -Fc > oan_$(date +%F).dump
docker compose exec -T postgres pg_restore -U postgres -d sandbox_db_oan --clean --if-exists < oan_2026-10-13.dump

# upgrade: pull/build new images; the api container applies new migrations on start
docker compose up -d --build

docker compose down        # stop (data kept)
docker compose down -v     # stop and DELETE all data volumes
```

Volumes: `oan_pgdata` (database), `oan_uploads` (participant ID proofs, certificates, product
icons/docs), `oan_api_logs` (API log files). Back up the first two.

### Refreshing the init snapshot

Run from a machine that has the source database. Use PostgreSQL 18 client tools to match the image:

```bash
pg_dump -h localhost -U postgres -d sandbox_db_oan --no-owner --no-privileges \
  --exclude-table=public.users \
  --exclude-table-data=public.participant_token --exclude-table-data=public.adm_token \
  --exclude-table-data=public.api_log --exclude-table-data=public.user_action_log \
  --exclude-table-data=public.sandbox_log \
  -f deployment/postgres/initdb/01-oan-sandbox-data.sql
gzip -9 -f deployment/postgres/initdb/01-oan-sandbox-data.sql
```

## 7. API gateway (existing APISIX)

The sandbox does not run the gateway. Set `GATEWAY_SANDBOX_URL` to the proxy (not the Admin
API) of the Apache APISIX already deployed for the environment, e.g.
`https://apisix-dev.example.org`; set `GATEWAY_UAT_URL` and `GATEWAY_PROD_URL` when those
gateways exist. The API container must be able to reach that URL.

Products flagged **Served through the API gateway** (the A2C products) are called on that URL:
the gateway URL plus the end-point path, with the headers the participant entered
(`Authorization`, `apikey`). The sandbox uses nothing gateway-specific, so no code or image
change is tied to the gateway product. The init step
`deployment/postgres/initdb/02-use-deployed-gateway.sql` clears end-point URLs copied from a
developer machine (`localhost`, `kong`), so every gateway call uses the configured gateway.

What the APISIX deployment must provide for the A2C products:

| Need | APISIX | Notes |
| --- | --- | --- |
| Routes | one route per A2C path, upstream = the A2C service | Paths must match the catalogue end-points |
| JWT | `jwt-auth`, consumer key = `oan_a2c_identity_gateway`, `key_claim_name: iss`, RS256 public key of A2C | APISIX looks for a `key` claim by default; A2C tokens carry the consumer in `iss` |
| API keys | `key-auth`, header `apikey` | Webhooks and dashboards |
| Consumer groups | `consumer-restriction` | Same groups as the A2C spec |
| IP allow-lists | `ip-restriction` | |
| Rate limits | `limit-count` (Redis policy when several APISIX nodes run) | A2C login: 5 per minute per IP |

**Laptop test.** Run a gateway on the Docker host and set
`GATEWAY_SANDBOX_URL=http://host.docker.internal:<proxy port>` (APISIX listens on `9080` by
default; the separate local test stack used so far listens on `8100`). `localhost` inside a
container is the container itself. Local gateway stacks are test tools only; they are not
deployed with the sandbox.

The A2C login rate limit is per IP, and every try-it call reaches the gateway from the API
container, so participants share that budget.

## 8. Notes

- No Redis container: the API has a `REDIS_ENABLED` setting but does not use Redis yet.
- Mail is off by default. Until SMTP is set, sign-up verification codes and reset links only
  appear in the API log (`docker compose logs api`).
- Images: `oan-sandbox-api` about 420 MB, `oan-sandbox-web` about 320 MB (Next.js standalone server).
