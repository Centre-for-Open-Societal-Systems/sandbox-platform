"""Admin invitations carry a copyable set-password link, so a new administrator can be
let in while mail is off."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.config.settings import settings

NEW_PASSWORD = "N3w#Admin2026"


def _create(client, admin_headers, master_admin, **extra):
    body = {"first_name": "Hana", "email_id": "hana@example.org", "login_name": "hana",
            "role_id": master_admin.role_id, **extra}
    response = client.post("/oan/admin/users", headers=admin_headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def _set_password(client, token):
    return client.post("/oan/admin/auth/set-password", json={"token": token, "new_password": NEW_PASSWORD})


def test_create_returns_a_working_set_password_link(client, admin_headers, master_admin, monkeypatch):
    monkeypatch.setattr(settings, "PORTAL_URL", "https://sandbox.example.org")
    user = _create(client, admin_headers, master_admin)

    invitation = user["invitation"]
    assert invitation["emailed"] is False  # mail is off in tests
    assert invitation["invite_url"].startswith("https://sandbox.example.org/admin/set-password?token=")
    assert user["is_activated"] is False

    assert _set_password(client, _token(invitation["invite_url"])).status_code == 200
    login = client.post("/oan/admin/auth/login", json={"username": "hana", "password": NEW_PASSWORD})
    assert login.status_code == 200, login.text
    # The link is single-use.
    assert _set_password(client, _token(invitation["invite_url"])).status_code == 404


def test_a_new_link_replaces_the_old_one(client, admin_headers, master_admin):
    user = _create(client, admin_headers, master_admin)
    old = _token(user["invitation"]["invite_url"])

    resent = client.post(f"/oan/admin/users/{user['admin_id']}/invite", headers=admin_headers)
    assert resent.status_code == 200, resent.text
    assert resent.json()["message"] == "Invitation link created."
    new = _token(resent.json()["data"]["invite_url"])
    assert new != old

    assert _set_password(client, old).status_code == 404
    assert _set_password(client, new).status_code == 200


def test_no_link_for_an_activated_user(client, admin_headers, master_admin):
    user = _create(client, admin_headers, master_admin, password="Given#Pass2026")
    assert user["invitation"] is None and user["is_activated"] is True

    resent = client.post(f"/oan/admin/users/{user['admin_id']}/invite", headers=admin_headers)
    assert resent.status_code == 400
    assert "already set a password" in resent.text
