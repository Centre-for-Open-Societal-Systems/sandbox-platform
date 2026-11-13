# OAN Sandbox — Docker deployment

The sandbox runs from one Compose file, `docker-compose.yml` in this folder. Nothing has to be
installed on the host except Docker Engine 24+ with Compose v2.

```
browser ──> web (Next.js)  :3005 ──> api (FastAPI) :8010 ──> postgres :5432 (inside the network)
                                         │
                                         └──> existing APISIX gateway  (GATEWAY_UAT_URL)
```

| Service | Image | Host port (default) | Purpose |
| --- | --- | --- | --- |
| `web` | built from `ui/Dockerfile` | `3005` | Public site, participant portal, admin console |
| `api` | built from `docker/sandbox-api/Dockerfile` (context: repo root) | `8010` | Sandbox API (`/oan/...`, health `/oan/health`) |
| `postgres` | `postgres:18-alpine` | `127.0.0.1:5433` | Database `sandbox_db_oan` |

**The API gateway is not part of this stack.** The API calls the Apache APISIX gateway already
deployed for the environment (dev, staging and so on) at `GATEWAY_UAT_URL`. The stack will
not start until that URL is set. Redis is not included either: the API does not use it (only
the gateway's rate limiting does).

## 1. First start

```bash
cd sandbox-platform
cp .env.example .env
#   set DB_PASSWORD, JWT_ACCESS_TOKEN_KEY, JWT_REFRESH_TOKEN_KEY
#   (python -c "import secrets; print(secrets.token_urlsafe(48))")
#   set PUBLIC_API_URL / ALLOWED_ORIGINS / PORTAL_URL to the public addresses
#   set GATEWAY_UAT_URL to the existing APISIX proxy URL of this environment
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
LOAD_DEMO_CATALOGUE=true      # optional: A2C (11 products) + OpenG2P demo product + Farmer Registry
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
| `GATEWAY_UAT_URL` | — (required) | Proxy URL of the **existing** APISIX for UAT; try-it calls for gateway products go here |
| `GATEWAY_ENABLED` | `true` | Route products flagged "Served through the API gateway" via APISIX |
| `GATEWAY_PROD_URL` | empty | External production gateway when it exists |
| `GATEWAY_UAT_PUBLIC_URL`, `GATEWAY_PROD_PUBLIC_URL` | empty (= the URL above) | The gateway as **partners** reach it; shown in code samples, the try-it request URL and API history (see §7) |
| `GATEWAY_SYNC_ENABLED`, `GATEWAY_TYPE` | `false`, `apisix` | **Pull from gateway** in the console; `apisix` or `kong` (see §7) |
| `GATEWAY_ADMIN_URL`, `GATEWAY_ADMIN_TOKEN` | empty | Gateway Admin API and its key, read by the pull (and written by app sync) |
| `GATEWAY_APP_SYNC_ENABLED` | `false` | Write participant apps to APISIX as consumers (see §7, *Apps and keys*) |
| `APP_CREDENTIAL_ENCRYPTION_KEY` | — (**Secret**, required in production) | Fernet key for stored app keys/secrets; never rotate it without re-issuing keys |
| `SANDBOX_MOCK_RESPONSES` | `false` | `true` lets try-it answer non-gateway endpoints from stored samples |
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

The sandbox does not run the gateway. Set `GATEWAY_UAT_URL` to the proxy (not the Admin
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

What it must provide for **Farmer Registry - Staff API** (catalogue product from
`deployment/farmer-registry/farmer_registry.postman_collection.json`):

| Gateway path (POST) | Upstream | Notes |
| --- | --- | --- |
| `/farmer-registry/auth/token` | `https://<keycloak>/realms/staff/protocol/openid-connect/token` | Form body; the staff user and client secret come from the registry team |
| `/farmer-registry/<path>` (12 paths in the collection) | `https://<farmer registry staff API>/<path>` | Strip the `/farmer-registry` prefix |
| CSRF | `proxy-rewrite` header `Cookie: X-CSRF-Token=$http_x_csrf_token` | The registry checks a header/cookie double-submit; partners send only the header |

The local generator `apisix-gateway/build_apisix_config.py` (`farmer_registry_adc`) writes this as an
ADC file with host placeholders; it can be used as the starting point for the environment's gateway.

**Laptop test.** Run a gateway on the Docker host and set
`GATEWAY_UAT_URL=http://host.docker.internal:<proxy port>` (APISIX listens on `9080` by
default; the separate local test stack used so far listens on `8100`). `localhost` inside a
container is the container itself. Local gateway stacks are test tools only; they are not
deployed with the sandbox.

**Public gateway URL.** The API calls the gateway on `GATEWAY_UAT_URL`; partners copy the
URL from the code samples into Postman or their own code. When the API reaches the gateway on
an address partners cannot use (`host.docker.internal`, a cluster service such as
`http://apisix-gateway.apisix:9080`), set `GATEWAY_UAT_PUBLIC_URL` (and the UAT/PROD ones)
to the public proxy URL, e.g. `https://apisix-dev.example.org`. Calls still go to the internal
URL; code samples, the try-it request URL and API history show the public one. Leave it empty
when both are the same. Laptop test: `GATEWAY_UAT_URL=http://host.docker.internal:9080`,
`GATEWAY_UAT_PUBLIC_URL=http://localhost:9080`.

**Pull from gateway.** With `GATEWAY_SYNC_ENABLED=true`, `GATEWAY_TYPE` (`apisix` or `kong`),
`GATEWAY_ADMIN_URL` and `GATEWAY_ADMIN_TOKEN` set, the console's API Catalogue shows a
**Pull from gateway** button. It reads every service and route from the Admin API
(APISIX `/apisix/admin/services|routes`, Kong `/services`, `/routes`, `/plugins`), shows a
preview, then on **Apply pull**:

- matches each route operation (method + path; `:id` and `(?<id>…)` become `{id}`) with the
  end-points served through the gateway;
- creates the new ones, unpublished, in the product already holding the service's end-point
  with the closest path, or else in a product per gateway service
  (`product.gateway_product_id`), with path parameters and the credential header taken from
  the route's auth plugin (`jwt-auth` / `key-auth`, or an `auth: bearer` label);
- fills in what existing end-points lack (name, description, path parameters, credential
  header) without overwriting an imported OpenAPI contract;
- lists end-points the gateway no longer serves, and wildcard / OPTIONS-only routes, without
  deleting anything.

Request and response samples are not on the gateway: import the app's OpenAPI spec on the
product for those. The API is `GET /oan/admin/gateway/status` and
`POST /oan/admin/gateway/sync` (`{"dry_run": true}` for the preview).

The A2C login rate limit is per IP, and every try-it call reaches the gateway from the API
container, so participants share that budget.

**Apps and keys.** Participants create apps (portal: *My Apps*), each with an API key and a
secret, and request **API products** (console: *API Products*, bundles of catalogue endpoints;
requests are decided in *Apps & Keys*). With `GATEWAY_APP_SYNC_ENABLED=true` every app is written
to APISIX through `GATEWAY_ADMIN_URL` as a consumer `oanapp_<id>` (label
`managed_by=oan-sandbox`): `key-auth` and `hmac-auth` credentials, and a `consumer-restriction`
whitelist of the routes its approved API products cover. So:

- the admin key needs **write** access to consumers (a viewer key only serves the pull);
- routes that should require an app key carry `key-auth` (`header: apikey`) and serve **one
  operation per route**, so an app can be granted a subset of them;
- set `APP_CREDENTIAL_ENCRYPTION_KEY` (Secret) before the first key is issued and keep it;
- a failed gateway write is kept on the app (*Sync failed*) and retried with *Re-sync gateway*.

### OAuth app tokens (`GATEWAY_PARTNER_AUTH=oauth`)

The mode used on dev. Partners do not send the API key per call: they exchange the app's
API key + secret for an access token at Keycloak (client credentials) and send only the
token in `X-Partner-Token`:

```bash
curl -X POST https://<keycloak>/realms/partner/protocol/openid-connect/token   --data-urlencode grant_type=client_credentials   --data-urlencode client_id=<API key> --data-urlencode client_secret=<API secret>
curl -X POST https://<partner host>/farmer-registry/register-data/get_register_summary_data   -H "X-Partner-Token: <access_token>" -H "Content-Type: application/json" -d '{...}'
```

- Nothing is written to the gateway: no consumers or credentials. The sandbox only reads
  the routes (a **viewer** admin key is enough). The consumer plugins of the API-key modes
  (app IP whitelist, per-product limits) do not exist; the routes do the same from the
  token: the app's whitelist is the claim `oan_ips`, the limits of its products
  (`GATEWAY_RATE_LIMIT_ENABLED`) `oan_limit_minute` / `oan_limit_day`, counted per API.
  A change applies from the next token (tokens live five minutes).
- API history of direct calls: the routes carry `http-logger` themselves (chart
  `oan-partner-gateway`, `callLog`) and name the app in each record (`app`, from the
  token). Set `GATEWAY_LOG_INGEST_ENABLED=true` and `GATEWAY_LOG_INGEST_TOKEN`; the same
  token goes to the APISIX pods as `OAN_SANDBOX_LOG_INGEST_AUTHORIZATION`
  (`Bearer <token>`). `GATEWAY_LOG_INGEST_URL` is not used in this mode: the URL is the
  chart's `callLog.url`.
- The sandbox writes every active app key to Keycloak as a confidential client
  (`oan-sandbox-provisioner` needs `manage-clients`; `setup_partner_realm.py` gives it) whose
  tokens carry `participant_uid`, `oan_app`, `oan_environments` and `oan_routes` (the APISIX
  route ids of the app's approved API products). Revoking a key or deleting an app deletes
  the client: no new token.
- The gateway routes check the token (realm JWKS, `iss`, `exp`, the environment role) and
  that the route is in `oan_routes`: `401` without or with a bad token, `403` for a route the
  app has no product for. Locally: `PARTNER_AUTH=oauth` in `../apisix-gateway`. On
  Kubernetes (APISIX Ingress Controller): chart
  [`deploy/apisix-partner-gateway/k8s`](deploy/apisix-partner-gateway/README.md).
- Settings: `GATEWAY_PARTNER_AUTH=oauth`, `GATEWAY_APP_SYNC_ENABLED=true`,
  `KEYCLOAK_PROVISIONING_ENABLED=true`, `KEYCLOAK_URL`, `KEYCLOAK_REALM=partner`,
  `KEYCLOAK_ADMIN_CLIENT_SECRET`; usually also `PARTICIPANT_AUTH_PROVIDER=keycloak` with
  `KEYCLOAK_LOGIN_CLIENT_SECRET`. The API refuses to start with oauth but without Keycloak
  provisioning or app sync.
- Try-it: **Get token** on the end-point page fetches the app's token (the secret stays on
  the server), shows the token request as its own curl, and puts the token in the
  `X-Partner-Token` header. Code samples show only the API call.

### UAT and production apps; production's own Keycloak and APISIX

**Apps belong to one environment and have their own keys.** Participants create UAT
apps. Once approved for production, *Move to production* on a UAT app (portal: My Apps)
makes a production copy - same name, same API products, its own description and IP whitelist -
that waits for an administrator (the app and each
product, whatever the product's approval type) and then gets its **own** API key + secret.
A UAT app's keys work only on UAT, a production app's only on production (token claim
`oan_environments`; try-it lists only the apps of the chosen environment, and starts in the
environment chosen in My Apps). A production app's keys stop working when the participant's
production access is taken away. The console's Apps & Keys filters by environment.

**Production request (account).** The partner sends its signing key: the X.509 certificate
(PEM / DER) or only its public key; the API refuses private keys, expired certificates,
RSA under 2048 bits and other curves (accepted: RSA ≥ 2048, EC P-256 / P-384, Ed25519) and a
pasted key that does not match the certificate. Approving production stores the key as the
partner's key, published at `/oan/partners/{partner_id}/jwks.json` for Partner Management.
The web app's CSP allows `frame-src blob:` so the console can preview uploaded PDFs in a dialog.

Each environment (cluster) has its own Keycloak and APISIX. The sandbox stays one portal;
UAT uses the main settings above, production gets its own. All are optional: **empty =
production apps use the main Keycloak / gateway** (still with their own keys and a token
naming only `production`).

| Setting | What it does |
| --- | --- |
| `GATEWAY_PROD_URL` (+ `GATEWAY_PROD_PUBLIC_URL`) | Try-it and code samples for PRODUCTION call this proxy (existing setting). |
| `GATEWAY_PROD_ADMIN_URL`, `GATEWAY_PROD_ADMIN_TOKEN` (Secret) | Production's Admin API (viewer key in oauth mode). Production apps' route ids are read from it; apikey / keycloak modes write production apps' consumers there. "Pull from gateway" gets a UAT / Production choice. |
| `KEYCLOAK_PROD_URL`, `KEYCLOAK_PROD_PUBLIC_URL` | Production's Keycloak (oauth mode): production apps' clients, and their "Get token". |
| `KEYCLOAK_PROD_REALM`, `KEYCLOAK_PROD_ADMIN_CLIENT_ID` | Empty = `KEYCLOAK_REALM` / `KEYCLOAK_ADMIN_CLIENT_ID`. |
| `KEYCLOAK_PROD_ADMIN_CLIENT_SECRET` (Secret) | Production's `oan-sandbox-provisioner` secret; required when `KEYCLOAK_PROD_URL` is set. |
| `KEYCLOAK_PROD_JWKS_URL` | Empty = `{KEYCLOAK_PROD_URL}/realms/{realm}/protocol/openid-connect/certs`. |

Participant users and the portal sign-in stay on the main Keycloak. Production apps
approved before production's own Keycloak / gateway was configured move there at their
next sync (any change, or *Re-sync gateway* in the console); their old clients / consumer
on the main ones are removed.

Production setup (DevOps):

1. Production Keycloak: `setup_partner_realm.py --url https://<prod keycloak> --realm partner`
   (creates `oan-sandbox-provisioner`); its secret goes into `KEYCLOAK_PROD_ADMIN_CLIENT_SECRET`.
2. Production APISIX: chart `oan-partner-gateway` with `environmentRole: production`, the
   production host and TLS, `keycloak.issuer` = production's realm, production upstreams.
3. The sandbox: `GATEWAY_PROD_URL`, `GATEWAY_PROD_ADMIN_URL` / `_TOKEN`, `KEYCLOAK_PROD_*`; the
   Admin API needs a certificate the API trusts (or an in-cluster URL).

### App key lifecycle

- **Secret shown once.** Lists never carry a secret. The owner sees it in clear when a key is
  issued or rotated, or once through *Reveal secret* (the first key is issued at approval, while
  the owner is away). Afterwards only a new key helps: *Rotate*.
- **Rotate.** A new key is issued at once; the old one keeps working for
  `APP_KEY_ROTATION_GRACE_DAYS` (0 = revoked at once), then expires. Needs a free key slot
  (`MAX_ACTIVE_CREDENTIALS_PER_APP`).
- **Expiry.** With `APP_KEY_LIFETIME_DAYS` above 0 every new key expires after that time. The API
  checks every `APP_KEY_MAINTENANCE_MINUTES`: it marks keys past their date *Expired*, removes them
  from the gateway (and Keycloak), and emails the owner `APP_KEY_EXPIRY_WARN_DAYS` ahead. Run one
  API replica per database, or accept that two replicas may both send a warning mail.
- **Emails** (`APP_KEY_ISSUED`, `_ROTATED`, `_REVOKED`, `_EXPIRING`, `_EXPIRED`; editable under
  console Content) never contain the key or the secret. A database seeded earlier uses the built-in
  text until the template is saved in the console.
- Migration `e6f0a4b2c3d8` adds the columns; the entrypoint runs `alembic upgrade head`. Existing keys
  stay valid; their secret can be revealed once more.

### Request ids, support SLA, retention, data export

- Every response carries `X-Request-Id` (same value as `X-Correlation-Id`). A caller may send either
  header (up to 64 plain characters); the id is in the access log and the audit trail.
- `SUPPORT_SLA_HOURS` (72): support queries get a due date; open ones past it show *Overdue* in the
  console and "we aim to answer by" in the portal. No new column, nothing changes for answered queries.
- **Support tickets are conversations** (migration `g8b2c6d4e0f3` converts existing tickets: the
  description becomes the first message, the reply the second). Participant and team write back and
  forth on the ticket; the team can also add *internal notes* that never reach the participant and send
  no mail. Status: Open, In progress, Answered (waiting for the participant), Closed. A participant's reply
  reopens an answered ticket and restarts its SLA clock; a closed ticket takes no replies. Tickets are
  numbered `TKT-000123` and show *unread* for whoever has not opened the latest message.
  - `SUPPORT_NOTIFY_EMAIL` (empty): mailbox told when a participant writes (template `QUERY_NEW_MESSAGE`).
  - `SUPPORT_AUTO_CLOSE_DAYS` (0 = never): answered tickets nobody replied to close by themselves.
  - `SUPPORT_MAX_MESSAGES_PER_TICKET` (100).
  - Mails to participants (template `QUERY_RESPONSE`) carry `Message-ID` / `In-Reply-To` / `References`
    headers and the ticket number, and each message records whether its mail went out
    (`notified_date`) and its Message-ID (`external_id`). Reading replies *from* mail is not built; the
    columns `channel` and `external_id` are where it plugs in. Existing databases keep their stored
    `QUERY_RESPONSE` text; edit it in the console (Content, Email templates) to add `{{ticket_no}}` and
    `{{ticket_url}}`.
- `AUDIT_LOG_RETENTION_DAYS` (0 = keep forever): the hourly maintenance run deletes older audit entries.
  Export what you must keep first (console, User tracking, Export).
- `GET /oan/participant/profile/export` (portal: Profile, *Download my data*): the account's own profile,
  apps (key prefixes only), queries, call history and activity as JSON. Deleting an account is a policy
  decision and is not built.

### Rate-limit headers and usage

With `GATEWAY_RATE_LIMIT_ENABLED`, APISIX (`limit-count`, checked against 3.18 source) adds
`X-Minute-RateLimit-Limit|Remaining|Reset` and `X-Day-RateLimit-Limit|Remaining|Reset` to each response
and answers `429` over the limit. It sends no `Retry-After`; partners use the matching `…-Reset`
(seconds). My Apps shows "Used today X of Y" from the call history (approximate; the gateway counts).

### Helm values for production (oan-helm, to add)

`oan-helm` is a separate repository; its `oan-sandbox` chart needs these, as `config` values and
Secret keys, next to the existing `config.gateway.*` / `config.keycloak.*` (check the exact names in
the chart's `values.yaml`):

```yaml
config:
  gateway:
    prodUrl: ""            # GATEWAY_PROD_URL
    prodPublicUrl: ""      # GATEWAY_PROD_PUBLIC_URL
    prodAdminUrl: ""       # GATEWAY_PROD_ADMIN_URL
  keycloak:
    prodUrl: ""            # KEYCLOAK_PROD_URL
    prodPublicUrl: ""      # KEYCLOAK_PROD_PUBLIC_URL
    prodRealm: ""          # KEYCLOAK_PROD_REALM
    prodAdminClientId: ""  # KEYCLOAK_PROD_ADMIN_CLIENT_ID
    prodJwksUrl: ""        # KEYCLOAK_PROD_JWKS_URL
  appKeys:
    lifetimeDays: 0        # APP_KEY_LIFETIME_DAYS
    rotationGraceDays: 7   # APP_KEY_ROTATION_GRACE_DAYS
    expiryWarnDays: 14     # APP_KEY_EXPIRY_WARN_DAYS
    maintenanceMinutes: 60 # APP_KEY_MAINTENANCE_MINUTES
# Secret (same Secret as DB_PASSWORD, ...): GATEWAY_PROD_ADMIN_TOKEN, KEYCLOAK_PROD_ADMIN_CLIENT_SECRET
```

Empty production values keep today's behaviour (production apps use the main Keycloak / gateway).

### Kubernetes (dev)

The dev deployment is the Helm chart `oan-sandbox` in
[oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/tree/main/charts/oan-sandbox):
values `environments/dev/values/sandbox.yaml`, steps and Secret keys in
`examples/dev/sandbox.yaml`, gateway steps in `docs/apisix-gateway.md` (section 8b). The
same settings as above are chart values (`config.gateway.*`, `config.keycloak.*`); secrets
come from one Secret (`DB_PASSWORD`, `JWT_*`, `APP_CREDENTIAL_ENCRYPTION_KEY`,
`KEYCLOAK_ADMIN_CLIENT_SECRET`, `KEYCLOAK_LOGIN_CLIENT_SECRET`, `GATEWAY_ADMIN_TOKEN`).

## 8. Notes

- No Redis container: the API has a `REDIS_ENABLED` setting but does not use Redis yet.
- Mail is off by default. Until SMTP is set, sign-up verification codes and reset links only
  appear in the API log (`docker compose logs api`). Admin invitations need no log: creating
  a console user without a password (or **New invitation link** on a user who has not set one)
  shows the set-password link in the console with a **Copy** button (single use, 24 hours).
- Images: `oan-sandbox-api` about 420 MB, `oan-sandbox-web` about 320 MB (Next.js standalone server).
