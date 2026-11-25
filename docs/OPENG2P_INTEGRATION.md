# OpenG2P integration: Partner Management and the Consent Manager

How the sandbox talks to OpenG2P Partner Management (PM) and the COSS Consent Manager
(CM), which versions it supports, and **what to do when OpenG2P changes them**.

- Contract (one file): [`backend/app/integrations/openg2p_contract.py`](../backend/app/integrations/openg2p_contract.py)
- Watcher: [`backend/scripts/openg2p/check_upstream.py`](../backend/scripts/openg2p/check_upstream.py),
  weekly in CI ([`.github/workflows/openg2p-upstream.yml`](../.github/workflows/openg2p-upstream.yml))
- Code: `app/integrations/partner_management.py`, `app/integrations/consent_manager_admin.py`,
  `app/services/partner_portal_service.py` (partners, keys), `app/services/pm_policy_service.py` (data policies)
- Tests: `tests/test_openg2p_versions.py`, `test_pm_policies.py`, `test_pm_production.py`, `test_partner_portal.py`

## 1. What the sandbox does

| Step | PM 1.0 (COSS today) | PM develop (OpenG2P G2P-5719, coming to COSS) |
|---|---|---|
| Participant approved (UAT; production in production's PM) | Onboarding request **once the partner has a signing key** (PM copies it from the sandbox JWKS, `import_from_jwks_url`); status `NO_KEY` until then | Onboarding request at once; PM reads the keys from the sandbox JWKS when needed (`keys_from_jwks_url`) |
| Partner changes its key | Key-update request (new key copied, old kid revoked) | Nothing: PM reads the JWKS |
| Approval of onboarding / key requests | `PM_AUTO_APPROVE` (UAT default yes), `PM_PROD_AUTO_APPROVE` (default no: PM staff) | same |
| API product with a data policy approved for an app | Filed in the **Consent Manager** (`POLICY_BACKEND=cm`/`auto`): binding per (partner audience, registry), new policy version; a widening waits for **AWE** | Filed in **PM** (`POLICY_BACKEND=pm`/`auto`): policy request; PM staff approve (UAT may auto-approve) |
| Policy dropped | CM binding suspended | PM revocation request |
| Use-case policies (`name@major`) | Not supported (shown as rejected) | Supported |
| Access taken away | PM partner disabled | same |

`auto` everywhere means: the code asks PM which release it is (`GET /metadata` exists on
develop only) and files policies in PM when it has them, else in the CM. So when COSS
installs the new PM, **only settings change**: `PM_API_VERSION` (or `auto`) and
`POLICY_BACKEND`. Policies already filed in the CM stay there (rows keep `backend=cm`);
decide with the data side whether to move them.

## 2. Settings

| Setting | Values | Note |
|---|---|---|
| `PM_API_VERSION`, `PM_PROD_API_VERSION` | `auto` (default), `1.0`, `develop` | per PM (UAT / production cluster) |
| `PM_AUTO_APPROVE`, `PM_PROD_AUTO_APPROVE` | `true` / `false` (default prod false) | sandbox approves its own PM requests |
| `POLICY_BACKEND` | `auto` (default), `pm`, `cm`, `none` | where API products' data policies go |
| `CM_ADMIN_API_URL`, `CM_ADMIN_TOKEN_URL`, `CM_ADMIN_CLIENT_ID`, `CM_ADMIN_CLIENT_SECRET` | | CM staff API; service account with `CONSENT_MANAGER_ADMIN` |
| `CM_PROD_ADMIN_*` | | production cluster's own CM |

## 3. Supported versions (pinned in the contract)

| Component | Branch | Pinned commit | Releases |
|---|---|---|---|
| PM profile `1.0` | `1.0` | `b5232da` | charts 1.0.2, 1.0.3 (same API) |
| PM profile `develop` | `develop` | `33dd782` | not released yet |
| COSS Consent Manager | `develop` | `32bce76` | |

## 4. When OpenG2P changes something

The weekly job fails with a report (job summary). Locally:

```bash
python backend/scripts/openg2p/check_upstream.py --cache .og2p-cache
```

Read the report:

1. **Commits touching the contract files** - read each (`git show <sha>` in the cache).
   Most need nothing; look for changed request bodies, statuses, routes, validation
   rules (e.g. 33dd782: "use-case policies take no allowed_purposes" → the sandbox
   refuses purposes on use cases in `PmPolicy` and `PM_DEFAULT_POLICIES`).
2. **BREAKING drift** - a field the sandbox sends or a route it calls is gone. Change
   `openg2p_contract.py` and the code that sends it, before that PM version is deployed.
3. **NEW fields** - optional upstream additions. Add them to the contract and
   `PmPolicy` (schemas/app.py) if products should set them; `tests/test_openg2p_versions.py`
   checks that `PmPolicy`'s fields equal `PM_POLICY_FIELDS`.
4. **A new release branch** (e.g. `1.1`) - add a `PmProfile` (capabilities + pinned ref +
   charts), its `PM_ONBOARDING_FIELDS` / `PM_ROUTES`, and a `WATCHED` entry; teach
   `pm.profile()` auto-detection if needed; add tests for its behaviour.

Then: run the backend tests, move the pinned `ref` in the contract to the commit you
checked, run the watcher again (it should say "up to date"), and note the change in
README "Project status".

## 5. Mapping notes

- PM `allow_partner_consents` ↔ CM `consent_method`: allowed → `partner_signed`, not
  allowed → `otp` (only consents the subject confirmed at the CM).
- CM `audience` = the participant's partner id (`oan-p-<id>`, the CM partner portal's
  `partner_id`); `partner_mgmt_id` = its PM id (`PARTNER_OAN_P_<id>`), whose keys the CM uses.
- An empty `allowed_signing_algs` becomes the algorithm of the partner's registered key
  (PM's and CM's own default, EdDSA/ES256, would refuse an RSA key).
