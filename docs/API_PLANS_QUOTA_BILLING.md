# API plans, quotas and postpaid billing (APISIX)

**Status:** Proposal, waiting for approval. Nothing here is built yet.
**Date:** 2026-10-29

This document answers three questions and proposes a design for the OAN Sandbox:

1. Can APISIX let one consumer make only a fixed number of calls (e.g. 2000)?
2. Can we sell plans such as **Bronze / Silver / Gold** with different limits?
3. Can we bill partners **postpaid** for what they used?

**Short answer:** 1 and 2 are done in APISIX itself (`limit-count`, optionally Consumer
Groups). APISIX **does not bill**. It counts, blocks and logs. Billing is built in the
sandbox from the call logs APISIX already sends.

## Contents

1. [Background: APISIX ports and terms](#1-background-apisix-ports-and-terms)
2. [What the sandbox does today](#2-what-the-sandbox-does-today)
3. [Limiting one consumer (e.g. 2000 calls)](#3-limiting-one-consumer-eg-2000-calls)
4. [Plans: Bronze / Silver / Gold](#4-plans-bronze--silver--gold)
5. [Postpaid billing](#5-postpaid-billing)
6. [Proposed design](#6-proposed-design)
7. [Implementation phases](#7-implementation-phases)
8. [Decisions needed](#8-decisions-needed)
9. [Risks and limits](#9-risks-and-limits)
10. [References](#10-references)

---

## 1. Background: APISIX ports and terms

| Port | What | Who uses it |
|---|---|---|
| `9080` | **Data plane**: the gateway. Partner and app API calls go through it | Partners, apps |
| `9180` | **Control plane**: Admin API `/apisix/admin/*` and Dashboard `/ui/` | Admins, sandbox backend |

The Dashboard (`/ui/`) is only a front end. Every screen calls the Admin API on the same port
with the admin key (`X-API-KEY`). Config is stored in **etcd**, and the gateway applies changes
at once, with no restart.

| Term | Meaning |
|---|---|
| **Consumer** | One API caller. In the sandbox, one consumer per app: `oanapp_<id>` |
| **Plugin** | A feature attached to a route, consumer or consumer group (auth, limits, logging, …) |
| **Consumer Group** | Shared plugin config that many consumers point to with `group_id` |
| **`limit-count`** | Plugin that counts calls in a time window and refuses the rest (`429`) |
| **`http-logger`** | Plugin that posts a record of every call to an HTTP endpoint |

---

## 2. What the sandbox does today

Source: `backend/app/services/app_gateway_service.py`.

Each app's consumer gets:

| Plugin | Purpose | Switch |
|---|---|---|
| `key-auth` / `hmac-auth` | App key + secret | always |
| `consumer-restriction` | Only the routes of the app's approved API products | always |
| `ip-restriction` | App IP whitelist | when the app has IPs |
| **`limit-count`** | Per-minute and per-day limits, the **most generous** of the app's approved API products | `GATEWAY_RATE_LIMIT_ENABLED` |
| **`http-logger`** | Every call posted to `POST /oan/internal/gateway/logs`, stored as API history (`source` DIRECT) | `GATEWAY_LOG_INGEST_ENABLED` |

`limit-count` today, built by `_limit_count()`:

```json
{
  "rules": [
    { "count": 60,   "time_window": 60,    "key": "${consumer_name} minute", "header_prefix": "Minute" },
    { "count": 5000, "time_window": 86400, "key": "${consumer_name} day",    "header_prefix": "Day" }
  ],
  "rejected_code": 429,
  "policy": "local | redis"
}
```

Limits come from the API product fields **Calls per minute, per app** and **Calls per day,
per app** (admin *API Products* form). Redis is used when
`GATEWAY_RATE_LIMIT_POLICY=redis` and `GATEWAY_RATE_LIMIT_REDIS_HOST` is set.

There is also a **usage report** (`backend/app/services/usage_service.py`) that counts calls
from `api_log` per partner, API, app, product, day or status code, with export.

**Missing:** monthly quota, plans, prices, invoices.

---

## 3. Limiting one consumer (e.g. 2000 calls)

### 3.1 Plain APISIX example

```http
PUT http://127.0.0.1:9180/apisix/admin/consumers/oanapp_42
X-API-KEY: <admin key>
Content-Type: application/json

{
  "username": "oanapp_42",
  "plugins": {
    "key-auth": { "key": "..." },
    "limit-count": {
      "count": 2000,
      "time_window": 2592000,
      "key_type": "var",
      "key": "consumer_name",
      "rejected_code": 429,
      "rejected_msg": "Monthly quota exhausted",
      "show_limit_quota_header": true,
      "policy": "redis",
      "redis_host": "redis",
      "redis_port": 6379
    }
  }
}
```

| Field | Meaning |
|---|---|
| `count: 2000` + `time_window: 2592000` | 2000 calls per 30 days. Call 2001 gets **429** |
| `show_limit_quota_header` | Responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |
| `policy: redis` | Counter kept in Redis. **Needed** when APISIX runs on more than one node or must keep counts across restarts. `local` = in memory per node |

### 3.2 Things to know

| Limit | Effect | How we handle it |
|---|---|---|
| `time_window` is required | No "2000 for ever" | Very large window for a one-time cap |
| The window starts at the **first call**, not on the 1st of the month | 30-day rolling, not calendar month | See 6.4: the sandbox puts the month in the counter key and re-syncs on the 1st |
| Counter is per key | Changing the key starts a new counter (a reset) | Used on purpose for the monthly reset |
| A consumer plugin **overrides** the same plugin on its Consumer Group | Group and consumer cannot both set `limit-count` | Sandbox keeps `limit-count` on the consumer (6.2) |

### 3.3 In the sandbox

The current `rules` list gets a third rule for the month:

```json
{ "count": 2000, "time_window": 2678400, "key": "${consumer_name} month 2026-10", "header_prefix": "Month" }
```

---

## 4. Plans: Bronze / Silver / Gold

### 4.1 Example plans

| Plan | Monthly quota | Per minute | Price (example) | Overage (postpaid) |
|---|---|---|---|---|
| **Free / Sandbox** | 2,000 | 10 | 0 | blocked at quota |
| **Bronze** | 20,000 | 30 | X / month | Y per 1,000 calls |
| **Silver** | 100,000 | 120 | X / month | Y per 1,000 calls |
| **Gold** | 500,000 | 600 | X / month | Y per 1,000 calls |

Numbers and prices are placeholders, for the business to decide.

### 4.2 Two ways in APISIX

| | A. Consumer Groups | B. Sandbox renders limits on each consumer (**recommended**) |
|---|---|---|
| How | `consumer_groups/gold` holds `limit-count`; consumer has `group_id: gold` | Plan stored in sandbox DB; gateway sync writes the plan's rules into the consumer's `limit-count` |
| Change a plan's limits | One edit on the group | Sandbox re-syncs every consumer on that plan |
| Combine with API product limits | Conflict: a consumer-level `limit-count` overrides the group's, so product limits and plan limits cannot both apply | Plan and product limits merged into one `rules` list |
| Monthly reset by calendar | Hard | Month in the key, re-sync on the 1st |
| Source of truth | Split between etcd and sandbox | Sandbox DB |

**Recommendation: B.** The sandbox already writes `limit-count` per consumer, so a plan is one
more input to the same code. Consumer Groups can still be used later for plan-wide plugins that
do not clash.

---

## 5. Postpaid billing

APISIX only **counts, blocks and logs**. Billing is built in the sandbox:

```
API call ─► APISIX :9080 ─► backend service
               │
               └─ http-logger ─► sandbox POST /oan/internal/gateway/logs
                                        │
                                        ▼
                               api_log (app, endpoint, status, time)   ← already exists
                                        │  nightly
                                        ▼
                               usage_daily (participant, app, product, day, calls)
                                        │  month end
                                        ▼
                               invoice (plan fee + overage) ─► admin review ─► email / PDF
```

### 5.1 Prepaid vs postpaid at the gateway

| Model | Gateway behaviour |
|---|---|
| **Prepaid / hard cap** | Block with 429 once the quota is used |
| **Postpaid** | Do **not** block at the plan quota. Count the extra calls as overage and bill them. Keep a **safety cap** (e.g. 3× quota) in `limit-count` only to protect the backends |

### 5.2 What counts as a billable call (to decide)

| Status | Suggested |
|---|---|
| `2xx` | billable |
| `4xx` from the backend (bad request) | billable or not, business decision |
| `401` / `403` / `429` from the gateway | **not** billable (refused before the backend) |
| `5xx` | **not** billable |
| try-it calls from the portal | **not** billable (already marked `X-OAN-Sandbox-Transaction`) |

### 5.3 Accuracy

- `http-logger` sends logs in batches. If the sandbox is down, APISIX retries, but logs can be
  lost after the retries. The invoice is built from `api_log`, so a gap means under-billing,
  never over-billing.
- APISIX's request id is unique, so a batch delivered twice is stored once (already handled in
  `gateway_log_service.py`).
- For strict billing, the counter in Redis can be read at month end and compared with
  `api_log` (reconciliation report).

---

## 6. Proposed design

### 6.1 New data

**`billing_plan`**

| Column | Example |
|---|---|
| `code`, `name` | `GOLD`, "Gold" |
| `monthly_quota` | 500000 (null = unlimited) |
| `per_minute_limit` | 600 |
| `billing_model` | `PREPAID_CAP` / `POSTPAID` |
| `monthly_fee`, `currency` | 0.00, `USD` |
| `overage_unit`, `overage_price` | 1000, 0.50 |
| `safety_cap_multiplier` | 3 (postpaid only) |
| `is_active`, `sort_order` | |

**`participant_plan`**: which plan a participant (or an app, see D2) is on, with history:

| Column | Purpose |
|---|---|
| `participant_id`, `plan_id` | |
| `valid_from`, `valid_to` | Upgrade / downgrade keeps history; the invoice uses the plan valid on each day |
| `changed_by`, `reason` | Audit |

**`usage_daily`**: nightly roll-up of `api_log`: `participant_id`, `app_id`, `api_product_id`,
`day`, `billable_calls`, `refused_calls`.

**`invoice`** + **`invoice_line`**: `participant_id`, `period` (`2026-10`), `plan_fee`,
`included_calls`, `used_calls`, `overage_calls`, `overage_amount`, `total`, `status`
(`DRAFT` → `ISSUED` → `PAID` / `VOID`), PDF file.

### 6.2 Gateway limits (extends `_limit_count`)

The consumer's `limit-count.rules` becomes:

| Rule | From |
|---|---|
| minute | the smaller of the plan's per-minute and the products' per-minute |
| day | the products' per-day (unchanged) |
| **month** | plan quota (prepaid) or quota × safety multiplier (postpaid). Key `${consumer_name} month <yyyy-mm>` |

Quota per **participant** (all apps share it) needs one counter key for the participant
instead of `${consumer_name}`: `participant <id> month <yyyy-mm>`. All of that participant's
consumers use the same key, so they share one counter in Redis. **Redis policy is required** for this.

### 6.3 Plan change

Admin changes the plan → `participant_plan` row closed and a new one opened → gateway re-sync
of the participant's apps → new limits apply at once. The counter is kept (same month key),
so an upgrade mid-month keeps the calls already used.

### 6.4 Monthly reset

A scheduled job at 00:00 UTC on the 1st re-syncs all consumers. The key changes from
`… month 2026-10` to `… month 2026-11`, so the counter starts at 0. The old key expires by
itself in Redis. `time_window` is 31 days so a key never expires mid-month.

### 6.5 Admin console

- **Billing → Plans:** create / edit plans (same template as *API Products*).
- **Participants → detail:** current plan, change plan, this month's usage vs quota.
- **Billing → Invoices:** month-end drafts, review, issue, mark paid, download PDF.
- **Usage report:** add plan and quota columns to the existing report.

### 6.6 Participant portal

- **Usage this month:** calls used / quota, a progress bar, and the days left.
- **Plan:** current plan, list of plans, "request upgrade" (admin approves).
- **Invoices:** list and PDF download.
- Email at 80 % and 100 % of quota.

---

## 7. Implementation phases

| Phase | Scope | Main files | Done when |
|---|---|---|---|
| **1. Monthly quota** | Month rule in `_limit_count`, month in key, 1st-of-month re-sync job, Redis policy on | `app_gateway_service.py`, scheduler | Call 2001 of the month gets 429; resets on the 1st |
| **2. Plans** | `billing_plan`, `participant_plan` + migrations; admin *Plans* page; plan on participant; sync uses plan limits | new `billing_plan_service.py`, admin UI | Changing a participant to Gold changes their consumer's rules |
| **3. Usage roll-up** | `usage_daily` nightly job; billable-status rules; usage vs quota in admin and portal; 80 % / 100 % emails | `usage_service.py`, portal UI | Portal shows the same numbers as the admin usage report |
| **4. Invoices** | Month-end draft invoices, admin review / issue / paid, PDF, email | new `invoice_service.py` | Draft invoice for each postpaid participant on the 1st |
| **5. Reconciliation** | Compare the Redis counter with `api_log`; report gaps | script + admin report | Gap report runs monthly |
| **6. Tests** | Unit tests for limits and invoice maths; gateway live test (extends `apisix-gateway/gateway_features_test.py`) | `backend/tests` | All green |

Each phase is a separate PR (`develop` → `develop`).

---

## 8. Decisions needed

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | Plan names, quotas, prices, currency | table in 4.1 | Business to fill |
| D2 | Quota per **participant** (all apps share) or per **app** | participant / app | **Participant**, because billing is per organisation |
| D3 | Month = calendar month or 30 days from start | calendar / rolling | **Calendar month** (matches invoices) |
| D4 | Postpaid over quota: block or bill overage | block / overage + safety cap | **Overage + safety cap 3×** |
| D5 | Billable statuses | see 5.2 | 2xx (+ backend 4xx if the business wants) |
| D6 | Who changes a plan | admin only / participant requests + admin approves | **Participant requests, admin approves** |
| D7 | Sandbox environment billed? | yes / no | **No.** Sandbox = Free plan; bill UAT / production only |
| D8 | Payment collection in the system? | invoice only / payment gateway | **Invoice only** at first; payments recorded by admin |

---

## 9. Risks and limits

- **Redis is required** for a correct monthly count across nodes and restarts. With `local`
  policy each gateway node counts on its own, and counts are lost on restart.
- **Log loss** under-bills (5.3). The reconciliation report in phase 5 shows it.
- **Clock / time zone:** the month boundary uses UTC. Partners in other zones see the reset at
  a different local time, so this should be written on the invoice.
- **Admin key:** the sandbox writes consumers through the Admin API. Keep port `9180` closed to
  the network and the key in `.env` only.
- **Exact behaviour to verify on our APISIX 3.18** before coding: `limit-count` `rules` with a
  31-day window and a literal month in `key`, and header names with `header_prefix`.

---

## 10. References

| Topic | Path / link |
|---|---|
| Current consumer plugins and `limit-count` | `backend/app/services/app_gateway_service.py` (`consumer_plugins`, `_limit_count`, `effective_limits`) |
| Gateway call logs | `backend/app/services/gateway_log_service.py` |
| Usage report | `backend/app/services/usage_service.py` |
| Rate-limit / log settings | `backend/app/config/settings.py` (`GATEWAY_RATE_LIMIT_*`, `GATEWAY_LOG_INGEST_*`) |
| Gateway live test | `Sandbox/apisix-gateway/gateway_features_test.py` |
| APISIX `limit-count` | https://apisix.apache.org/docs/apisix/plugins/limit-count/ |
| APISIX Consumer Groups | https://apisix.apache.org/docs/apisix/terminology/consumer-group/ |
| APISIX `http-logger` | https://apisix.apache.org/docs/apisix/plugins/http-logger/ |
