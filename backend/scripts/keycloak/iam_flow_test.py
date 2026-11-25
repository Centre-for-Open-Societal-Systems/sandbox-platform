"""Live check: a participant's Keycloak user from sign-up to delete.

Needs the sandbox API (default http://localhost:8010/oan) with
KEYCLOAK_PROVISIONING_ENABLED, the realm from setup_partner_realm.py, and
mail off (sign-ups wait for admin approval). Steps:

1. sign up a test participant -> no Keycloak user yet, so no token;
2. admin approves UAT -> user created, enabled with role ``uat``, but without
   a password (the sandbox only stores a hash), so still no token;
3. the participant signs in to the portal -> Keycloak gets the password; the
   password grant on the shared client returns a token whose claims name the
   participant and list the environment;
4. change password -> old password refused by Keycloak, new one works;
5. admin disables the participant -> token refused;
6. cleanup: participant deleted (user disabled), then the Keycloak user is
   deleted with the Keycloak admin login when KC_ADMIN_PASSWORD is set.

    OAN_ADMIN_PASSWORD=... KC_ADMIN_PASSWORD=... python scripts/keycloak/iam_flow_test.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid

import httpx

SANDBOX = os.environ.get("SANDBOX_URL", "http://localhost:8010/oan")
KEYCLOAK = os.environ.get("KC_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "oan-partners")
CLIENT = os.environ.get("KEYCLOAK_PARTNER_CLIENT_ID", "oan-partner-api")
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def data(response: httpx.Response) -> dict:
    assert response.status_code < 300, f"{response.request.method} {response.request.url}: {response.text[:300]}"
    return response.json()["data"]


def token(username: str, password: str) -> httpx.Response:
    return httpx.post(
        f"{KEYCLOAK}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": CLIENT, "username": username, "password": password},
    )


def claims(response: httpx.Response) -> dict:
    part = response.json()["access_token"].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def main() -> None:
    http = httpx.Client(timeout=60)
    admin = data(http.post(f"{SANDBOX}/admin/auth/login", json={
        "username": os.environ.get("OAN_ADMIN_EMAIL", "admin@openagrinet.org"),
        "password": os.environ["OAN_ADMIN_PASSWORD"]}))
    ah = {"x-access-token": admin["access_token"], "x-auth-key": admin["auth_key"]}

    email, password = f"iam.e2e.{uuid.uuid4().hex[:6]}@example.org", "IamE2e#2026"
    signup = data(http.post(f"{SANDBOX}/participant/auth/signup", json={
        "first_name": "Iam", "last_name": "Check", "country_code": "ET", "mobile_number": "+251911000777",
        "email_id": email, "category_id": 1, "company_name": "IAM Check PLC", "password": password,
        "declaration": True}))
    assert not signup["requires_verification"], "run with mail off: the sign-up should wait for approval"
    pending = data(http.post(f"{SANDBOX}/admin/participants/pending?environment=UAT", headers=ah,
                             json={"search": email}))["participants"]
    participant_id = pending[0]["participant_id"]

    account = data(http.get(f"{SANDBOX}/admin/participants/{participant_id}/iam-account", headers=ah))["account"]
    check("sign-up created no Keycloak user (made at UAT approval)", account is None, str(account))
    check("no token before approval", token(email, password).status_code in (400, 401))

    data(http.post(f"{SANDBOX}/admin/participants/approve", headers=ah,
                   json={"participant_id": participant_id, "environment": "UAT"}))
    account = data(http.get(f"{SANDBOX}/admin/participants/{participant_id}/iam-account", headers=ah))["account"]
    check("approval created the user, enabled, with role uat",
          bool(account) and account["status"] == "ACTIVE" and account["roles"] == ["uat"]
          and bool(account["keycloak_id"]), str(account))
    check("no password (so no token) until the portal sign-in",
          not account["password_synced"] and token(email, password).status_code in (400, 401))

    login = data(http.post(f"{SANDBOX}/participant/auth/login", json={"email_id": email, "password": password}))
    ph = {"x-access-token": login["access_token"], "x-auth-key": login["auth_key"]}
    account = data(http.get(f"{SANDBOX}/admin/participants/{participant_id}/iam-account", headers=ah))["account"]
    check("portal sign-in handed Keycloak the password", account["password_synced"], str(account))

    issued = token(email, password)
    check("password grant on the shared client issues a token", issued.status_code == 200, issued.text[:160])
    if issued.status_code == 200:
        c = claims(issued)
        check("token names the participant and lists the environment",
              c.get("participant_uid") == signup["unique_id"] and c.get("oan_environments") == ["uat"],
              str(c)[:200])

    new_password = "IamE2e#2026-changed"
    data(http.post(f"{SANDBOX}/participant/auth/change-password", headers=ph, json={
        "old_password": password, "new_password": new_password, "confirm_password": new_password}))
    check("password change reaches Keycloak: old refused, new works",
          token(email, password).status_code == 401 and token(email, new_password).status_code == 200)

    data(http.post(f"{SANDBOX}/admin/participants/toggle", headers=ah, json={"id": participant_id, "is_enabled": False}))
    check("disabled participant -> token refused", token(email, new_password).status_code in (400, 401))

    keycloak_id = account["keycloak_id"]
    http.delete(f"{SANDBOX}/admin/participants/{participant_id}", headers=ah)
    if os.environ.get("KC_ADMIN_PASSWORD"):
        kc = httpx.post(f"{KEYCLOAK}/realms/master/protocol/openid-connect/token", data={
            "grant_type": "password", "client_id": "admin-cli",
            "username": os.environ.get("KC_ADMIN_USER", "admin"), "password": os.environ["KC_ADMIN_PASSWORD"]}).json()
        gone = httpx.delete(f"{KEYCLOAK}/admin/realms/{REALM}/users/{keycloak_id}",
                            headers={"Authorization": f"Bearer {kc['access_token']}"})
        check("cleanup: Keycloak user deleted", gone.status_code == 204, str(gone.status_code))

    print(f"\n{'all checks passed' if not failures else f'{failures} check(s) failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
