"""One-time Keycloak setup of the sandbox apps' realm (KEYCLOAK_APPS_REALM).

Sandbox apps are machines: each app key is an OAuth client (client credentials)
whose token the partner gateway checks. They get a realm of their own, apart
from the partners' users (KEYCLOAK_REALM: portal sign-in, the Consent Manager
partner portal), so that:

* the gateway trusts only this realm's issuer: a user's or another client's
  token from the users' realm opens nothing at the gateway, and back;
* the sandbox's service account here may manage clients only - it has no user
  roles - and the one in the users' realm no longer needs to manage clients
  (``setup_partner_realm.py --users-only`` takes ``manage-clients`` away there);
* the realm has machine settings: no login, no registration, no users,
  5-minute tokens, brute-force protection, and new clients get no profile /
  email / roles scopes (only ``basic``: sub, and the sandbox's ``oan:`` scopes).

Creates or updates:

* the realm (default ``partner-sandbox-app``);
* the confidential service-account client ``oan-sandbox-app-provisioner`` with
  exactly the realm-management roles view-clients, query-clients,
  manage-clients. Its secret is written to the given .env files (with
  KEYCLOAK_APPS_REALM and KEYCLOAK_APPS_ADMIN_CLIENT_ID), never printed.

The same script sets up production's own Keycloak (``--url`` of that one; then
the settings are KEYCLOAK_PROD_REALM / KEYCLOAK_PROD_ADMIN_CLIENT_*: give
``--prod``).

    KC_ADMIN_USER=admin KC_ADMIN_PASSWORD=... python scripts/keycloak/setup_app_realm.py \\
        --url http://localhost:8080 --env-file ../.env --env-file .env

Then: Apps & Keys > Re-sync all (each app's clients move here; the copies in the
users' realm are removed), the partner gateway's ``keycloak.issuer`` becomes
``<public Keycloak URL>/realms/<this realm>``, and after that
``setup_partner_realm.py --users-only``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

PROVISIONER_ROLES = ("view-clients", "query-clients", "manage-clients")
#: Realm default client scopes new clients may keep (the token's sub).
KEEP_DEFAULT_SCOPES = {"basic"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("KC_URL", "http://localhost:8080"))
    parser.add_argument("--realm", default="partner-sandbox-app")
    parser.add_argument("--client-id", default="oan-sandbox-app-provisioner")
    parser.add_argument("--token-lifespan", type=int, default=300, help="App access-token lifetime (s)")
    parser.add_argument("--env-file", action="append", default=[], help="Write the realm settings here")
    parser.add_argument("--prod", action="store_true", help="Write KEYCLOAK_PROD_* instead of KEYCLOAK_APPS_*")
    args = parser.parse_args()
    user, password = os.environ.get("KC_ADMIN_USER", "admin"), os.environ.get("KC_ADMIN_PASSWORD")
    if not password:
        print("Set KC_ADMIN_PASSWORD (the Keycloak admin user's password).", file=sys.stderr)
        return 2

    base = args.url.rstrip("/")
    token = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": user, "password": password},
        timeout=15,
    )
    token.raise_for_status()
    http = httpx.Client(base_url=f"{base}/admin/realms", timeout=30,
                        headers={"Authorization": f"Bearer {token.json()['access_token']}"})
    realm = args.realm
    machine = {
        "displayName": "OAN sandbox apps",
        "enabled": True,
        "sslRequired": "external",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "rememberMe": False,
        "loginWithEmailAllowed": False,
        "bruteForceProtected": True,
        "accessTokenLifespan": args.token_lifespan,
    }
    if http.get(f"/{realm}").status_code == 404:
        http.post("", json={"realm": realm, **machine}).raise_for_status()
        print(f"realm '{realm}' created")
    else:
        http.put(f"/{realm}", json={**http.get(f"/{realm}").json(), **machine}).raise_for_status()
        print(f"realm '{realm}' exists: machine settings applied")

    _trim_default_scopes(http, realm)
    provisioner = _provisioner(http, realm, args.client_id)
    users = http.get(f"/{realm}/users", params={"max": 5, "briefRepresentation": "true"}).json()
    people = [u["username"] for u in users if not u["username"].startswith("service-account-")]
    if people:
        print(f"NOTE: this realm has user accounts ({', '.join(people)}); app realms should have none.")

    secret = http.get(f"/{realm}/clients/{provisioner}/client-secret").json()["value"]
    prefix = "KEYCLOAK_PROD" if args.prod else "KEYCLOAK_APPS"
    for env_file in args.env_file:
        _set_env(Path(env_file), f"{prefix}_REALM", realm)
        _set_env(Path(env_file), f"{prefix}_ADMIN_CLIENT_ID", args.client_id)
        _set_env(Path(env_file), f"{prefix}_ADMIN_CLIENT_SECRET", secret)
        print(f"{prefix}_REALM, {prefix}_ADMIN_CLIENT_ID, {prefix}_ADMIN_CLIENT_SECRET written to {env_file}")
    if not args.env_file:
        print("No --env-file given: read the secret in the Keycloak console (Clients > Credentials).")
    print(f"issuer for the partner gateway (keycloak.issuer): <public Keycloak URL>/realms/{realm}")
    print(f"done: {base}/admin/master/console/#/{realm}/clients")
    return 0


def _trim_default_scopes(http: httpx.Client, realm: str) -> None:
    """New clients get no profile / email / roles / ... scopes: app tokens carry only
    sub (basic) and the sandbox's oan: scopes. Existing clients are not changed."""
    removed = []
    for kind in ("default-default-client-scopes", "default-optional-client-scopes"):
        for scope in http.get(f"/{realm}/{kind}").json():
            if scope["name"] not in KEEP_DEFAULT_SCOPES:
                http.delete(f"/{realm}/{kind}/{scope['id']}").raise_for_status()
                removed.append(scope["name"])
    print("realm default client scopes: only " + ", ".join(sorted(KEEP_DEFAULT_SCOPES))
          + (f" (removed: {', '.join(sorted(set(removed)))})" if removed else ""))


def _provisioner(http: httpx.Client, realm: str, client_id: str) -> str:
    clients = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
    if not clients:
        http.post(f"/{realm}/clients", json={
            "clientId": client_id,
            "name": "OAN sandbox (manages app clients)",
            "enabled": True,
            "publicClient": False,
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "fullScopeAllowed": False,
            "redirectUris": [],
            "webOrigins": [],
        }).raise_for_status()
        clients = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
        print(f"client '{client_id}' created")
    provisioner = clients[0]["id"]

    account = http.get(f"/{realm}/clients/{provisioner}/service-account-user").json()["id"]
    management = http.get(f"/{realm}/clients", params={"clientId": "realm-management"}).json()[0]["id"]
    path = f"/{realm}/users/{account}/role-mappings/clients/{management}"
    available = {r["name"]: r for r in http.get(f"/{realm}/clients/{management}/roles").json()}
    current = {r["name"]: r for r in http.get(path).json()}
    extra = [role for name, role in current.items() if name not in PROVISIONER_ROLES]
    if extra:
        http.request("DELETE", path, json=extra).raise_for_status()
    http.post(path, json=[available[name] for name in PROVISIONER_ROLES]).raise_for_status()
    # fullScopeAllowed is off: the realm-management roles must be in the client's scope
    # to appear in its token.
    scope_path = f"/{realm}/clients/{provisioner}/scope-mappings/clients/{management}"
    http.post(scope_path, json=[available[name] for name in PROVISIONER_ROLES]).raise_for_status()
    print(f"service account roles: {', '.join(PROVISIONER_ROLES)}"
          + (f" (removed: {', '.join(r['name'] for r in extra)})" if extra else ""))
    return provisioner


def _set_env(path: Path, name: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{name}={value}"
    if re.search(rf"^{name}=.*$", text, flags=re.M):
        text = re.sub(rf"^{name}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
