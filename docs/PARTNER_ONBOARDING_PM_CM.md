# Sandbox participants → Partner Management, Consent Manager and Keycloak

**Status:** Proposal, waiting for approval. Nothing here is built yet.
**Date:** 2026-10-29

This document explains how a partner is set up today in COSS / OpenG2P so it can call the
partner APIs (Consent Manager consent requests and the Aggregation Layer search). It then
proposes how a participant who registers on the OAN Sandbox gets the same setup
automatically.

## Contents

1. [Summary](#1-summary)
2. [How a partner is set up today](#2-how-a-partner-is-set-up-today)
3. [How a partner calls the APIs](#3-how-a-partner-calls-the-apis)
4. [What the sandbox does today](#4-what-the-sandbox-does-today)
5. [Gaps](#5-gaps)
6. [Proposed design](#6-proposed-design)
7. [Implementation phases](#7-implementation-phases)
8. [Decisions needed](#8-decisions-needed)
9. [Risks and open questions](#9-risks-and-open-questions)
10. [Source references](#10-source-references)

---

## 1. Summary

A partner needs **three separate things** to call the partner APIs. They live in three
different systems, and today **all three are set up by hand**:

| # | System | What it holds | Answers the question |
|---|---|---|---|
| 1 | **Keycloak** (`partner` realm) | A login user with the attribute `partner_id` and role `PARTNER_OPERATOR` / `PARTNER_ADMIN` | *Who is calling?* (bearer token) |
| 2 | **Partner Management (PM)** | The partner and its **public signing key(s)** | *Is this signature really theirs?* |
| 3 | **Consent Manager (CM)** | A **binding** (partner → data controller) and a versioned **policy** | *What may this partner access?* |

Partner Management **does not write to Keycloak**. It stores partners and keys only in its own
database. The Keycloak partner user is created separately (CM script `setup-partner-realm.sh`
or the Keycloak admin console).

The sandbox today creates its own Keycloak users and APISIX apps, but **sends nothing to PM
or CM**. That is why sandbox participants do not appear in Partner Management and cannot
raise consent requests.

**Proposal:** when a participant is approved, the sandbox backend files the partner into PM,
creates the CM binding and policy, and gives the participant's existing Keycloak user a
`partner_id` claim. PM and CM admins still approve (maker-checker).

---

## 2. How a partner is set up today

### 2.1 Partner Management (`COSS/partner-management`)

Central registry of partners and their **public keys**. Other modules (CM, registries) fetch
keys from it instead of keeping their own partner tables.

| Item | Detail |
|---|---|
| Tables | `pm_partners`, `pm_partner_keys`, `pm_partner_requests` |
| Partner fields | `partner_id` (unique, e.g. `PARTNER_BANK_A`), `name`, `org_name`, `description`, `jwks_url` |
| Key formats | PEM, X.509 certificate or JWK pasted, or imported once from `jwks_url`. Algorithms RS256 / ES256 / EdDSA |
| Partner lifecycle | `created` → (admin approves) `active` → `disabled`. Keys are served only for `active` partners |
| Key lifecycle | `pending` → `active` → `revoked`. Several keys can be active together for zero-downtime rotation |
| Policy | **None.** PM does not know what a partner may access |
| Admin auth | Keycloak **staff** realm token with role `partner_manager` |
| Local ports | key API `8050`, admin (staff-portal) API `8051`, UI `3003` |

**Admin APIs (staff token):**

| Method | Path | Purpose |
|---|---|---|
| POST | `/partners/requests/onboarding` | File an onboarding request (partner + initial keys) |
| POST | `/partners/requests/key-update` | File a key rotation (add / revoke keys) |
| GET | `/partners/requests` | List requests |
| POST | `/partners/requests/{id}/approve` | Approve, which activates the partner and keys |
| POST | `/partners/requests/{id}/reject` | Reject |
| GET | `/partners`, `/partners/{partner_id}` | List / detail |
| POST | `/partners/{partner_id}/disable` / `enable` | Stop / resume serving keys |

**Public key API (no auth, fail-closed with 404):**

| Method | Path |
|---|---|
| GET | `/keys/{partner_id}` |
| GET | `/keys/{partner_id}/{kid}` |
| GET | `/keys/{partner_id}/jwks.json` |

### 2.2 Consent Manager (`COSS/consent-management`)

CM owns **what a partner may access**. Its "partner" row is not the partner record. It is a
**binding** of a PM partner to one data controller, with a versioned policy.

**Binding** (`partners` table), unique per (`audience`, `controller_id`):

| Field | Meaning |
|---|---|
| `audience` | The id the partner presents (e.g. `bank-a`). Must equal the Keycloak `partner_id` claim |
| `controller_id` | The data controller (registry), e.g. Farmer Registry, or `aggregation_layer` |
| `partner_mgmt_id` | The PM `partner_id` (e.g. `PARTNER_BANK_A`), used to fetch keys from PM |
| `status` | `active` / `suspended` |

**Policy** (`partner_policies` table), versioned per binding:

| Field | Meaning |
|---|---|
| `allowed_data_scopes` | Ceiling of data blocks the partner can be granted |
| `allowed_purposes` | Allowed purposes |
| `allowed_subject_id_types` | e.g. `national_id` |
| `allowed_signing_algs` | Algorithms allowed for the partner's signatures |
| `max_validity_duration` | e.g. `P1Y` |
| `fetch_type` / `max_fetch_frequency` | `oneshot` / `periodic` |
| `data_life` | How long the partner may keep data |
| `consent_method` | `otp` / `partner_signed` / `internal` |
| `status` | `pending` → `active` → `superseded`; or `rejected` / `failed` / `stale` |

A policy that **widens** access is created `pending` and sent to the **Approval Workflow
Engine (AWE)**. It goes `active` only after approval.

**Admin APIs (role `CONSENT_MANAGER_ADMIN`):**

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/consent/v1/partners` | List / create bindings |
| GET / PATCH | `/consent/v1/partners/{id}` | Detail / update (e.g. suspend) |
| PUT / GET | `/consent/v1/partners/{id}/policy` | Set / read the active policy |
| GET | `/consent/v1/partners/{id}/policies` | All versions |
| POST | `/consent/v1/partners/{id}/policies/{version}/resubmit` | Resubmit a failed / stale / rejected version |

### 2.3 Keycloak `partner` realm

Created by CM's Helm `keycloak-init` plus the script
`consent-management/deployment/scripts/setup-partner-realm.sh` (locally:
`local-run/keycloak/keycloak_init.py`):

- realm roles `PARTNER_OPERATOR`, `PARTNER_ADMIN`
- user-profile attribute `partner_id`
- protocol mapper that puts `partner_id` into the token
- partner users, created by hand:

```bash
./setup-partner-realm.sh --namespace agrix --user bank-a-operator:bank-a:PARTNER_OPERATOR
```

### 2.4 How the three are linked

The links are only **matching values**, typed by hand:

```
Keycloak user attribute  partner_id = bank-a
                                         │  must equal
CM binding               audience   = bank-a
CM binding               partner_mgmt_id = PARTNER_BANK_A
                                         │  must equal
PM partner               partner_id = PARTNER_BANK_A   (+ public keys)
```

---

## 3. How a partner calls the APIs

### 3.1 Which credential each API checks

| API | What it checks | Comes from |
|---|---|---|
| CM `POST /consent/v1/partner-portal/consent-requests` (+ `verify-otp`, `consents`, …) | Bearer token from the **partner** realm, with a `partner_id` claim and a partner role | Keycloak |
| AL `POST /dci/registry/sync/search` with `authorize.consent_id` | Bearer token from the partner realm. `partner_id` must equal `header.sender_id` | Keycloak |
| AL `POST /dci/registry/sync/search` with `authorize.consent_jws` | **No token.** The consent object is signed with the partner's **private key**. CM checks it with the public key from PM | PM |
| Registries (DCI search) | JWS signature | PM |
| CM `POST /consent/v1/consent-requests` (non-portal) | **Staff** realm token. For staff / service accounts, not partners | — |

At every call, CM also checks the **binding + active policy**. Anything outside the policy is
refused (`scope_exceeds_policy`, `partner or policy not found`).

### 3.2 End-to-end flow

```
Partner                                   Consent Manager
───────                                   ───────────────
(1) POST /consent/v1/partner-portal/consent-requests   (partner-realm token)
                                     ──►  checks binding + policy, sends OTP to the farmer
(2) POST .../consent-requests/{id}/verify-otp
                                     ──►  consent recorded → consent_id

                                          Aggregation Layer
                                          ─────────────────
(3) POST /dci/registry/sync/search
    consent_id + token  OR  consent_jws ──►  CM /consent/v1/validate
                                               (policy + farmer consent;
                                                signature checked with PM key)
                                          ──►  registries, in parallel
    ◄── signed on-search (bene-360) ──────
```

---

## 4. What the sandbox does today

When the admin approves a participant (`backend/app/services/participant_service.py`,
`approve_environment`):

1. Sets the approval flags for the environment (sandbox / UAT / production).
2. `iam_user_service.sync`: Keycloak user in realm **`oan-partners`** (coss-keycloak `:8080`),
   with client roles of the shared client `oan-partner-api`.
3. `app_gateway_service.sync_participant_apps`: APISIX consumers for the participant's apps.
4. Email + audit.

The **Move to Production** request already collects a **public key** (`extra_data.public_key`),
and `participant.public_key` exists in the model.

**Nothing is sent to Partner Management or Consent Manager.**

---

## 5. Gaps

| # | Gap | Effect |
|---|---|---|
| G1 | No PM integration | Sandbox participants do not appear in Partner Management; no keys, so `consent_jws` cannot be verified |
| G2 | No CM binding / policy | Consent requests fail with `partner or policy not found` |
| G3 | No mapping from sandbox **API product** → CM `controller_id` / scopes / purposes | The sandbox cannot build a policy |
| G4 | `oan-partners` users have no `partner_id` claim or partner role, and CM / AL trust a different realm | Tokens of sandbox participants are refused by CM partner-portal and AL `consent_id` |
| G5 | Blocking / deleting a participant does not reach PM / CM | A blocked participant could keep access |
| G6 | CM open work listed by the AL (`aggregation-layer/docs/CM-API-CONTRACT.md`): send OTP when the request is raised; one partner-facing "verify OTP and approve" call | Not sandbox work, but the end-to-end flow depends on it |

---

## 6. Proposed design

### 6.1 Principles

- **Sandbox is the entry point.** Participants register and are approved once, in the
  sandbox.
- **PM and CM stay the source of truth** for keys and policy. The sandbox only **files
  requests** to them through their admin APIs. It never writes their databases.
- **Maker-checker is kept.** The sandbox files the request and the PM / CM admins approve.
- **One login per participant.** Reuse the existing `oan-partners` Keycloak user. No second
  user, no second password.
- **Idempotent and retryable.** Every push can be re-run; failures are recorded and shown,
  never silently lost.

### 6.2 Identifiers

| Value | Format (proposed) | Example |
|---|---|---|
| Keycloak `partner_id` attribute = CM `audience` | participant code, lower-case | `p-000123` |
| PM `partner_id` = CM `partner_mgmt_id` | `PARTNER_` + participant code, upper-case | `PARTNER_P_000123` |
| PM key `kid` | `<participant code>-<yyyymmdd>` | `p-000123-20261029` |

### 6.3 New sandbox data

**Table `participant_partner_link`**, one row per participant per environment:

| Column | Purpose |
|---|---|
| `participant_id`, `environment` | Owner |
| `pm_partner_id` | PM `partner_id` |
| `pm_request_id`, `pm_status` | Last PM request and its status (`created` / `approved` / `rejected` / `failed`) |
| `cm_audience` | CM audience (= Keycloak `partner_id`) |
| `last_error`, `last_synced_at` | Shown in the admin console; used for retry |

**Table `participant_cm_binding`**, one row per CM binding:

| Column | Purpose |
|---|---|
| `participant_id`, `environment`, `controller_id` | Binding key |
| `cm_binding_id`, `policy_version`, `policy_status` | From CM |
| `api_product_id` | Which sandbox API product caused it |
| `last_error`, `last_synced_at` | Retry / display |

**API product → CM mapping**, new optional fields on the sandbox API product
(admin form *API Products*):

| Field | Example |
|---|---|
| `cm_controller_id` | `aggregation_layer` |
| `cm_data_scopes` | `["FARMER_REGISTRY.farmer_personal_details"]` |
| `cm_purposes` | `["agri_credit"]` |
| `cm_consent_method` | `otp` |
| `cm_max_validity` | `P1Y` |

Only products with `cm_controller_id` set create CM bindings. Plain gateway products are
unchanged.

### 6.4 Flows

**A. Participant approved for an environment**

```
Sandbox admin approves
   │
   ├─ (existing) Keycloak user + APISIX apps
   ├─ (new) Keycloak: set attribute partner_id, add role PARTNER_OPERATOR
   └─ (new) PM: POST /partners/requests/onboarding  {partner_id, name, org, keys}
               → link.pm_status = created   (PM admin approves in PM UI)
```

**B. API product with CM mapping approved for an app**

```
Sandbox admin approves product access
   │
   ├─ CM binding exists for (audience, controller_id)?  no → POST /consent/v1/partners
   └─ PUT /consent/v1/partners/{id}/policy  (scopes = union of the participant's approved
                                             products for that controller)
         → widening → pending in AWE        (CM admin approves)
```

**C. Key change** (participant uploads a new public key in the portal)

```
PM: POST /partners/requests/key-update  {keys:[new], revoke_kids:[old]}   (PM admin approves)
```

**D. Participant blocked / deleted**

```
PM: POST /partners/{id}/disable      CM: PATCH binding status=suspended
Keycloak: disable user (existing)
```

**E. Status refresh**

A periodic job (or a "Refresh" button) reads PM request status and CM policy status and
updates the link tables.

### 6.5 Service accounts the sandbox needs

| Target | Credential | Role |
|---|---|---|
| PM admin API | Keycloak **staff** realm confidential client, e.g. `oan-sandbox-pm` | `partner_manager` |
| CM admin API | Keycloak **staff** realm confidential client, e.g. `oan-sandbox-cm` | `CONSENT_MANAGER_ADMIN` (CM has no narrower role) |
| Keycloak `oan-partners` | existing admin client used by `iam_user_service` | manage users |

Secrets go in the sandbox `.env`, never in code or Git.

### 6.6 CM / AL configuration change (Keycloak option 1)

Point CM and AL partner auth at the sandbox's `oan-partners` realm:

```
CONSENT_MANAGER_PARTNER_AUTH_ISSUER   = <keycloak>/realms/oan-partners
CONSENT_MANAGER_PARTNER_AUTH_JWKS_URL = <keycloak>/realms/oan-partners/protocol/openid-connect/certs
AGGREGATION_LAYER_PARTNER_AUTH_ISSUER / _JWKS_URL = same
```

and in realm `oan-partners`: declare the user-profile attribute `partner_id`, add the
`partner_id` mapper to client `oan-partner-api`, create realm roles `PARTNER_OPERATOR` and
`PARTNER_ADMIN`. These are the same steps `setup-partner-realm.sh` runs for the `partner` realm.

**Option 2 (not recommended):** the sandbox also creates a second user in CM's own `partner`
realm. That means two logins and two passwords per participant, which must be kept in sync.

### 6.7 Admin console changes (sandbox)

- **Participants → detail:** a new *Partner Management / Consent* panel showing the PM
  partner id, PM status, CM bindings with policy version and status, last error, and a
  **Retry** button.
- **API Products → edit:** an optional *Consent Manager* section with the fields in 6.3.
- **Participant portal:** upload or rotate the public key; show "Waiting for Partner
  Management approval" or "Active".

---

## 7. Implementation phases

| Phase | Scope | Main files | Done when |
|---|---|---|---|
| **1. PM sync** | `participant_partner_link` table + migration; PM client (staff token); onboarding on approval; status refresh; admin panel | new `partner_mgmt_service.py`, `participant_service.approve_environment`, alembic | Approved participant appears in PM UI as `created`; after PM approval `/keys/{id}` serves the key |
| **2. Keys** | Portal key upload / rotation → PM key-update; validation of the PEM | participant portal UI, `partner_mgmt_service.py` | Rotation shows old + new key active, then old revoked |
| **3. CM binding + policy** | API product CM fields; `participant_cm_binding` table; binding + policy push; AWE status refresh | `api_product_service.py`, new `consent_binding_service.py`, admin *API Products* form | Consent request via partner portal API passes the policy check |
| **4. Partner token** | `partner_id` attribute + mapper + role in `oan-partners`; CM / AL issuer config | `iam_user_service.py`, Keycloak init script, CM / AL env | Participant token is accepted by CM partner-portal and AL `consent_id` search |
| **5. Lifecycle** | Block / delete → PM disable + CM suspend; unblock → enable | `participant_service.py` | Blocked participant gets 404 from `/keys` and is refused by CM |
| **6. Tests** | Unit tests with mocked PM / CM; Postman e2e: register → approve → PM approve → CM approve → consent request → AL search | `backend/tests`, `postman/` | All green locally |

Each phase is a separate PR (`develop` → `develop`).

---

## 8. Decisions needed

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | When to push the partner to PM? | (a) at sandbox approval (b) at UAT / production approval | **(b)**, because the public key is collected in the production request. (a) would need the key at sign-up |
| D2 | Who approves in PM / CM? | (a) PM / CM admins approve (b) sandbox auto-approves | **(a)**, keeping maker-checker |
| D3 | `partner_id` format | see 6.2 | `PARTNER_<CODE>` in PM, `<code>` as audience |
| D4 | One PM / CM per environment, or shared? | (a) separate UAT and Prod (b) one shared | Depends on the deployment; the design supports both via `environment` |
| D5 | Keycloak for partner tokens | (1) reuse `oan-partners` users (2) second user in CM `partner` realm | **(1)**, one login per participant |
| D6 | Who maintains the API product → CM scope mapping? | sandbox admin in the API Products form, or a config file | **Sandbox admin form** |

---

## 9. Risks and open questions

- **CM admin role is broad.** CM has no narrower service role than `CONSENT_MANAGER_ADMIN`,
  so the sandbox's CM client must be held as tightly as an admin account.
- **Caches.** CM caches PM keys for 300 s and policies for about 60 s. A new key or policy can
  take up to five minutes to take effect.
- **CM open work (G6).** Until CM sends the OTP on request creation and adds a partner-facing
  "verify and approve" call, the end-to-end consent flow uses the subject's routes.
- **Issuer check (to confirm).** Verify on a running stack which issuer CM and AL accept after
  the change in 6.6, including the `iss` host (`localhost` vs docker network name).
- **Existing participants.** A one-time backfill script would push already-approved
  participants to PM / CM.
- **IAM.** `openg2p-iam-staff-api` handles staff login only. No partner registration flow was
  found in it. If partners are registered through another IAM screen, it needs to be reviewed.

---

## 10. Source references

| Topic | Path |
|---|---|
| PM overview and APIs | `COSS/partner-management/core/api/README.md` |
| PM models | `COSS/partner-management/core/api/src/openg2p_partner_management_api/models/partner.py`, `request.py` |
| PM local ports / auth | `COSS/partner-management/docker-compose.yml` |
| CM binding + policy model | `COSS/consent-management/backend/src/openg2p_consent_manager/models/partner.py` |
| CM partner / policy admin API | `.../controllers/partner_controller.py` |
| CM partner-portal API (partner token) | `.../controllers/partner_portal_controller.py` |
| CM consent request checks | `.../services/lifecycle_service.py` (`create_request`) |
| CM partner realm setup | `COSS/consent-management/deployment/scripts/setup-partner-realm.sh` |
| AL flow and contract | `COSS/aggregation-layer/README.md`, `docs/CM-API-CONTRACT.md` |
| AL partner token check | `COSS/aggregation-layer/backend/src/openg2p_aggregation_layer/auth.py` (`partner_from_token`) |
| AL onboarding example | `COSS/aggregation-layer/scripts/register-aggregator.py` |
| Sandbox approval | `oansandbox/backend/app/services/participant_service.py` (`approve_environment`) |
| Sandbox Keycloak users | `oansandbox/backend/app/services/iam_user_service.py` |
