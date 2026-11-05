# APISIX integration: apps, API products and keys

How the sandbox turns a participant's app into an APISIX consumer, which Admin API
calls it makes and when, and how to add a new endpoint so the right apps (and only
those) can call it.

- **Audience:** developers and DevOps working on the sandbox or the gateway.
- **Last updated:** 27 Oct 2026.
- **Code:**
  - `backend/app/integrations/gateway.py` (Admin API client)
  - `backend/app/services/app_gateway_service.py` (what is written)
  - `backend/app/services/app_service.py`, `api_product_service.py`, `participant_service.py` (when it is written)

## Contents

1. [Overview](#1-overview)
2. [Concepts](#2-concepts)
3. [Who owns what in APISIX](#3-who-owns-what-in-apisix)
4. [Admin API calls made by the sandbox](#4-admin-api-calls-made-by-the-sandbox)
5. [The consumer the sandbox writes](#5-the-consumer-the-sandbox-writes)
6. [When the sandbox calls APISIX](#6-when-the-sandbox-calls-apisix)
7. [Other traffic between the sandbox and APISIX](#7-other-traffic-between-the-sandbox-and-apisix)
8. [How an endpoint is matched to a route](#8-how-an-endpoint-is-matched-to-a-route)
9. [Adding a new endpoint](#9-adding-a-new-endpoint)
10. [Configuration](#10-configuration)
11. [Viewing it in the APISIX UI](#11-viewing-it-in-the-apisix-ui)
12. [Testing](#12-testing)
13. [Troubleshooting](#13-troubleshooting)
14. [FAQ](#14-faq)

---

## 1. Overview

```
 Participant portal / Admin console
              │  (sandbox API, :8010/oan)
              ▼
 ┌───────────────────────────┐   Admin API (:9180)   ┌──────────────────────────┐
 │ Sandbox API               │ ────────────────────▶ │ APISIX                    │
 │  apps, keys, API products │   consumers + keys    │  routes  (from sync.sh)   │
 │  approvals (database)     │ ◀──────────────────── │  consumers (from sandbox) │
 └───────────────────────────┘   call logs (http-    └────────────┬─────────────┘
              │                  logger callback)                 │ proxy (:9080)
              │ try-it calls (proxy :9080, apikey header)         ▼
              └───────────────────────────────────────▶  Upstream APIs (A2C,
                                                         grievance, Farmer Registry)
```

- The **sandbox decides** who may call what: apps, API products and approvals live in its database.
- **APISIX enforces** it on every call.
- The sandbox never creates or edits routes. It only writes **consumers** (one per app) and their **credentials** (one per API key).

## 2. Concepts

| Term | Where it lives | Meaning |
|---|---|---|
| **Route** | APISIX | One API operation, for example `POST /farmer-registry/register-data/search_in_a_register`, with `key-auth`. Created by `apisix-gateway/sync.sh`. |
| **Catalogue endpoint** | Sandbox | The same operation as shown in the portal. Created by *API Catalogue → Pull from gateway*. |
| **API product** | Sandbox | A bundle of catalogue endpoints that an admin publishes, for example `farmer-registry-read` (7 read endpoints plus the token endpoint). Approval is *Automatic* or *Admin approves*. |
| **App** | Sandbox | A participant's system. It has API keys, and it requests API products. |
| **Subscription** | Sandbox | App × API product, with a status: `PENDING`, `APPROVED`, `REJECTED` or `REVOKED`. Only `APPROVED` grants access. |
| **Consumer** | APISIX | One per app, named `oanapp_<app unique id without dashes>` and labelled `managed_by: oan-sandbox`. |
| **Credential** | APISIX | One pair per active API key: `<credential uid>-key` (`key-auth`) and `<credential uid>-hmac` (`hmac-auth`). |

**Rule of thumb:** a route existing in APISIX does not mean anyone can call it. An app can call a route only when that route's id is in its consumer's whitelist. That happens only through an approved API product.

## 3. Who owns what in APISIX

| APISIX object | Owner | How it changes | Edit in the APISIX UI? |
|---|---|---|---|
| Routes, services, upstreams | `apisix-gateway/build_apisix_config.py` → `sync.sh` (ADC) | Rebuild and sync | **No**: the next sync overwrites it |
| Partner consumers (`openg2p_consent_webhook`, `telco_ivr_lead_gateway`, `oan_dashboards`, `a2c_identity_platform`) | `sync.sh` | Rebuild and sync; keys come from `apisix-gateway/.env` | **No** |
| App consumers `oanapp_*` and their credentials | Sandbox API | Automatically, on the actions in [section 6](#6-when-the-sandbox-calls-apisix) | **No**: a re-sync overwrites it, and the sandbox database would disagree |

## 4. Admin API calls made by the sandbox

- **Base URL:** `GATEWAY_ADMIN_URL` (locally `http://host.docker.internal:9180`).
- **Header:** `X-API-KEY: <GATEWAY_ADMIN_TOKEN>`.

| # | Method and path | Purpose | Function |
|---|---|---|---|
| 1 | `GET /apisix/admin/routes` | Read every route (id, methods, paths) to map endpoints to route ids. Paginated, 500 per page. | `gateway.list_routes()`, `gateway.fetch()` |
| 2 | `GET /apisix/admin/services` | Read services. Used only by *Pull from gateway*. | `gateway.fetch()` |
| 3 | `PUT /apisix/admin/consumers` | Create or fully replace an app's consumer and its plugins. | `gateway.put_consumer()` |
| 4 | `DELETE /apisix/admin/consumers/{username}` | Remove the consumer. All of its keys stop working at once. | `gateway.delete_consumer()` |
| 5 | `GET /apisix/admin/consumers/{username}/credentials` | List the consumer's credentials, to find stale ones. | `gateway.list_credential_ids()` |
| 6 | `PUT /apisix/admin/consumers/{username}/credentials/{id}` | Write one credential (`key-auth` or `hmac-auth`). | `gateway.put_credential()` |
| 7 | `DELETE /apisix/admin/consumers/{username}/credentials/{id}` | Remove a revoked key's credential. | `gateway.delete_credential()` |

### One "sync" of an app (`app_gateway_service.sync_app`)

**If the app is active** (not deleted, status `ACTIVE`) **and its participant is enabled, sandbox-approved, not rejected and not deleted:**

1. `GET /routes`: skipped when several apps are synced together, because the routes are read once.
2. Work out the route ids the app's approved products cover ([section 8](#8-how-an-endpoint-is-matched-to-a-route)).
3. `PUT /consumers` with the plugins from [section 5](#5-the-consumer-the-sandbox-writes).
4. For every active key, `PUT /credentials/{uid}-key` and `PUT /credentials/{uid}-hmac`.
5. `GET /credentials`, then `DELETE` every credential that is no longer wanted.

**Otherwise:** `DELETE /consumers/{username}`.

The result is stored on the app: `gateway_status` is `SYNCED`, `FAILED` or `DISABLED`, along with `gateway_routes` and `gateway_warnings`. A failure never blocks the user's action. It is recorded, and an admin can press **Re-sync**.

## 5. The consumer the sandbox writes

```json
{
  "username": "oanapp_3f2a…",
  "desc": "OAN sandbox app 'My CRM' (participant 42)",
  "labels": { "managed_by": "oan-sandbox", "app_uid": "…", "participant_id": "42", "environment": "sandbox" },
  "plugins": {
    "consumer-restriction": { "type": "route_id", "whitelist": ["<route id>", "…"], "rejected_code": 403 },
    "ip-restriction":       { "whitelist": ["203.0.113.10/32"] },
    "limit-count":          { "rules": [ { "count": 60, "time_window": 60, "key": "${consumer_name} minute" },
                                         { "count": 5000, "time_window": 86400, "key": "${consumer_name} day" } ],
                              "rejected_code": 429, "policy": "local" },
    "http-logger":          { "uri": "<GATEWAY_LOG_INGEST_URL>", "auth_header": "Bearer …", "batch_max_size": 100 }
  }
}
```

| Plugin | Present when | Effect |
|---|---|---|
| `consumer-restriction` | Always | Only the whitelisted route ids pass; any other route returns **403**. With no approved route, the whitelist is `oan-sandbox-no-route`, so nothing passes. |
| `ip-restriction` | The app has an IP whitelist | Calls from other addresses get **403**. |
| `limit-count` | `GATEWAY_RATE_LIMIT_ENABLED=true` and an approved product has limits | The most generous per-minute and per-day limit of the approved products applies. Beyond it, **429**. |
| `http-logger` | `GATEWAY_LOG_INGEST_ENABLED=true` | Each call is reported back to the sandbox ([section 7](#7-other-traffic-between-the-sandbox-and-apisix)). |

Credentials:

```json
PUT …/credentials/<uid>-key   { "plugins": { "key-auth":  { "key": "<api key>" } } }
PUT …/credentials/<uid>-hmac  { "plugins": { "hmac-auth": { "key_id": "<api key>", "secret_key": "<api secret>" } } }
```

Keys and secrets are stored encrypted in the sandbox (`APP_CREDENTIAL_ENCRYPTION_KEY`) and decrypted only to be written here.

## 6. When the sandbox calls APISIX

"Sync" means the sequence in [section 4](#one-sync-of-an-app-app_gateway_servicesync_app).

### Participant portal

| User action | Sandbox API | APISIX effect |
|---|---|---|
| Create an app | `POST /oan/participant/apps` | Sync: the consumer and the first key are created. |
| Change the app's IP whitelist | `PUT /oan/participant/apps/{app_id}` | Sync. Changing only the name or description makes no call. |
| Delete an app | `DELETE /oan/participant/apps/{app_id}` | `DELETE` consumer |
| Request API products | `POST /oan/participant/apps/{app_id}/products` | Sync. *Automatic* products are whitelisted at once; *Admin approves* ones wait for approval. |
| Withdraw an API product | `DELETE /oan/participant/apps/{app_id}/products/{product_id}` | Sync: the product's routes leave the whitelist. |
| Issue a new key | `POST /oan/participant/apps/{app_id}/credentials` | Sync: the new credentials are written. |
| Revoke a key | `DELETE /oan/participant/apps/{app_id}/credentials/{credential_id}` | Sync: that key's credentials are deleted. |

### Admin console: Apps & Keys

| Admin action | Sandbox API | APISIX effect |
|---|---|---|
| Approve, reject or revoke a product for an app | `POST /oan/admin/apps/{app_id}/products/{product_id}/approve` (or `/reject`, `/revoke`) | Sync: the whitelist changes. |
| Revoke the whole app | `POST /oan/admin/apps/{app_id}/revoke` | `DELETE` consumer |
| Restore the app | `POST /oan/admin/apps/{app_id}/restore` | Sync: the consumer is back. |
| Re-sync | `POST /oan/admin/apps/{app_id}/gateway-sync` | Sync (repairs drift) |

### Admin console: API Products

| Admin action | Sandbox API | APISIX effect |
|---|---|---|
| Create a product | `POST /oan/admin/api-products` | None: no app subscribes to it yet. |
| Change a product's endpoints or limits | `PUT /oan/admin/api-products/{api_product_id}` | **Every app subscribed to the product is synced.** Routes are read once. Only `APPROVED` subscriptions gain the new routes. |

### Admin console: Participants

| Admin action | Sandbox API | APISIX effect |
|---|---|---|
| Disable or enable a participant | `POST /oan/admin/participants/toggle` | All of the participant's apps are synced. Disabling removes their consumers; enabling restores them. |
| Reject a participant's sandbox access | `POST /oan/admin/participants/reject` | All consumers are removed, and the participant is signed out. |
| Approve a participant's sandbox access | `POST /oan/admin/participants/approve` | All consumers are restored. |
| Delete a participant | `DELETE /oan/admin/participants/{participant_id}` | All consumers are removed. |

### Admin console: API Catalogue

| Admin action | Sandbox API | APISIX effect |
|---|---|---|
| Pull from gateway | `POST /oan/admin/catalog/gateway/sync` | Read only: `GET /services` and `GET /routes`. It creates or updates catalogue endpoints and **writes nothing to APISIX**. |

## 7. Other traffic between the sandbox and APISIX

| Direction | Call | When |
|---|---|---|
| Sandbox → APISIX proxy | `GATEWAY_UAT_URL` + endpoint path (locally `http://host.docker.internal:9080/...`), with the app's key in the `apikey` header and `X-OAN-Sandbox-Transaction` | A participant presses **Run** in try-it. |
| APISIX → sandbox | `POST /oan/internal/gateway/logs` with `Authorization: Bearer <GATEWAY_LOG_INGEST_TOKEN>` | After calls made directly with an app key, sent in batches every `GATEWAY_LOG_FLUSH_SECONDS`. They appear in API History with source **Direct**. |

## 8. How an endpoint is matched to a route

`app_gateway_service.resolve_routes`:

1. Collect the endpoints of the app's **approved** API products.
2. Keep only endpoints served through the gateway: the endpoint or its catalogue product must be flagged "served through the gateway". An endpoint with its own upstream URL never reaches APISIX.
3. Compare each endpoint's `(method, path)` with every APISIX route's `(methods × uris)`.
4. Grant a route id **only if every operation the route serves is in the app's products**. If a route serves two paths and only one is granted, the route is not granted, and a warning says *split the route per operation*. This is why every key-protected route has exactly one operation.
5. An endpoint that no route serves produces the warning *no gateway route serves it*.

The warnings appear on the app in the admin console (`gateway_warnings`).

## 9. Adding a new endpoint

Example: two new Farmer Registry operations.

### Step 1: create the routes in APISIX

1. Add both requests to `deployment/farmer-registry/farmer_registry.postman_collection.json`. Each URL must start with `{{STAFF_API_BASE}}`, because that prefix is how staff routes are recognised.
2. Rebuild and sync, from `apisix-gateway/`:
   ```bash
   python build_apisix_config.py   # writes generated/farmer-registry.adc.yaml
   sh sync.sh farmer-registry      # needs apisix-gateway/.env
   ```
   Each operation becomes its own route `farmer-registry-<name>`, with `key-auth` and a per-consumer `limit-count`.

> **Never create routes by hand in the APISIX UI.** A route without `key-auth` has no consumer, so `consumer-restriction` does not apply and the route is open to everyone.

### Step 2: bring them into the catalogue

In the admin console, go to **API Catalogue → Pull from gateway → Apply**. The two operations become catalogue endpoints under *Farmer Registry*.

### Step 3: grant them through an API product

| Option | Use when | Result |
|---|---|---|
| **A. Add them to an existing product**, for example `farmer-registry-full` | Every partner who already has that product should get them | Saving the product syncs all its subscribed apps. Apps with an **approved** subscription can call the new endpoints at once, with their existing keys and no new request. Pending, rejected and revoked subscriptions do not get them. |
| **B. Create a new product** with only these endpoints (*Admin approves*, published) | Only selected partners should get them | A partner requests the product for an app, and the admin approves it. Only that app's consumer gains the two route ids. |

Points to remember:

- An endpoint that is in the catalogue but **in no API product cannot be called by anyone** (403).
- A product that needs a bearer token must also include its **token endpoint**, for example `POST /farmer-registry/auth/token`, or apps cannot obtain the token.
- Partners are **not notified** by email when a product gains endpoints.

## 10. Configuration

Sandbox API settings (`.env`, passed through `docker-compose.yml`):

| Setting | Purpose | Local value |
|---|---|---|
| `GATEWAY_ENABLED` | Try-it calls go through the gateway | `true` |
| `GATEWAY_UAT_URL` | Gateway proxy as the API reaches it | `http://host.docker.internal:9080` |
| `GATEWAY_UAT_PUBLIC_URL` | Gateway as participants reach it, shown in code samples | `http://localhost:9080` |
| `GATEWAY_SYNC_ENABLED` | Enables *Pull from gateway* | `true` |
| `GATEWAY_APP_SYNC_ENABLED` | Write apps to APISIX as consumers. When off, apps live only in the sandbox (`gateway_status: DISABLED`). | `true` |
| `GATEWAY_ADMIN_URL`, `GATEWAY_ADMIN_TOKEN` | Admin API and key. The key is `APISIX_ADMIN_KEY` in `apisix-gateway/.env`. | `http://host.docker.internal:9180`, secret |
| `GATEWAY_APP_KEY_HEADER` | Header that `key-auth` reads | `apikey` |
| `APP_CREDENTIAL_ENCRYPTION_KEY` | Encrypts stored keys and secrets. Required except with `ENV=local`. | secret |
| `GATEWAY_RATE_LIMIT_ENABLED`, `GATEWAY_RATE_LIMIT_POLICY` | Adds `limit-count` from the product limits | see `.env` |
| `GATEWAY_LOG_INGEST_ENABLED`, `GATEWAY_LOG_INGEST_URL`, `GATEWAY_LOG_INGEST_TOKEN` | Adds `http-logger` and its callback | see `.env` |

The gateway's own secrets (admin key, keyring, partner keys, upstream tokens) are in `apisix-gateway/.env`; see `apisix-gateway/README.md`.

## 11. Viewing it in the APISIX UI

- **URL:** <http://127.0.0.1:9180/ui/>. It opens only on this machine.
- **Login:** the `APISIX_ADMIN_KEY` from `apisix-gateway/.env`.

| UI page | What to look at |
|---|---|
| Routes | Route ids, URIs and plugins (`key-auth`, `limit-count`) |
| Consumers | `oanapp_*` (labelled `managed_by: oan-sandbox`) and the partner consumers |
| Consumer → Plugins | `consumer-restriction.whitelist`, `ip-restriction`, `limit-count`, `http-logger` |
| Consumer → Credentials | `<uid>-key` and `<uid>-hmac` for each active key |

**Use the UI to look, not to change.** Changes there are overwritten by `sync.sh` or by a sandbox re-sync ([section 3](#3-who-owns-what-in-apisix)).

## 12. Testing

### Automated

| Test | Location | Covers |
|---|---|---|
| Unit tests (fake gateway) | `backend/tests/test_apps.py`, `test_security_audit.py` | Consumer contents, whitelist from approved products, key rotation, removal when a participant is disabled, deleted or rejected |
| `smoke_test.py` | `apisix-gateway/` | Every route: key required, partner keys limited to their own route |
| `apps_flow_test.py` | `apisix-gateway/` | Products → app → 403 before approval → approve → pass → revoke, rotate and delete keys |
| `gateway_features_test.py` | `apisix-gateway/` | IP whitelist (403), rate limit (429), direct-call logs |
| `sandbox_flow_test.py` | `apisix-gateway/` | Try-it as an app, API History, redaction |

Run the gateway tests from `apisix-gateway/` with the sandbox venv, leaving 60 s between runs because of the A2C login limit:

```bash
export OAN_ADMIN_EMAIL=admin@openagrinet.org OAN_ADMIN_PASSWORD='<admin password>'
PY=../oansandbox/backend/venv/Scripts/python.exe
$PY smoke_test.py; $PY apps_flow_test.py; $PY gateway_features_test.py; $PY sandbox_flow_test.py
```

### Manual walk-through (portal and APISIX UI side by side)

1. **Portal → My Apps → Create app.** Choose an *Automatic* product. In the APISIX UI, the new `oanapp_…` consumer appears, with that product's route ids in its whitelist.
2. **Call a granted route** with the app key (`apikey` header). The call passes the gateway.
3. **Call a route that is not granted** with the same key: **403**.
4. **Request an *Admin approves* product.** Nothing changes in APISIX yet. **Approve it in the console** (Apps & Keys), and the whitelist grows.
5. **Set an IP whitelist** on the app. The consumer gains `ip-restriction`, and a call from another IP gets 403.
6. **Revoke the key** in the portal. Its credential disappears, and calls with it get 401.
7. **Disable the participant** in the console. The consumer disappears. Enable the participant, and it is back.

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| **401** "Missing API key" or "Invalid API key" | No `apikey` header; key revoked; app deleted; participant disabled or rejected | Use an active key of an active app |
| **403** "This app has no access to this API. Request the API product that includes it." | The route is not in the app's whitelist: product not approved, endpoint not in any product, or the route serves more operations than the product covers | Approve the product, add the endpoint to it, or split the route; check `gateway_warnings` |
| **403** from `ip-restriction` | The caller's IP is not in the app's whitelist | Add the IP, or clear the whitelist |
| **429** | `limit-count` reached | Wait, or raise the product's limit |
| App shows `gateway_status: FAILED` | The Admin API was unreachable, or the key was wrong when it was synced | Check `GATEWAY_ADMIN_URL` and the token, then press **Re-sync** |
| App shows `DISABLED` | `GATEWAY_APP_SYNC_ENABLED=false` | Turn it on and re-sync |
| A new route is callable with no key at all | The route was made without `key-auth`, probably by hand | Recreate it through `build_apisix_config.py` → `sync.sh` |
| A route returns a 401 from the upstream (Farmer Registry) | The registry needs its own staff bearer token | Expected until the registry credentials are set up |

## 14. FAQ

**If a new route is in APISIX but not pulled into the sandbox, can an existing app call it?**
No. Its route id is not in any consumer's whitelist, so APISIX answers 403, even to someone who knows the URL. This assumes the route has `key-auth`; see [section 9](#9-adding-a-new-endpoint).

**When I add endpoints to an existing product, do existing apps get them?**
Yes, apps whose subscription to that product is **approved** get them as soon as the product is saved. They keep using their existing keys.

**Does the sandbox create or change APISIX routes?**
No. Routes come only from `sync.sh`. The sandbox writes consumers and credentials.

**Why one route per operation?**
A route is granted only when the app's products cover all of its operations. A shared route would force granting everything it serves, or nothing.

**What does the Keycloak user of a participant do at the gateway?**
Nothing yet. APISIX does not check Keycloak tokens; APIs open with the app's API key. The admin console still shows the Keycloak user.
