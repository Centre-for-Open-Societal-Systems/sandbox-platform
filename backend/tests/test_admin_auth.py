"""Admin authentication and authorisation."""

from __future__ import annotations

from tests.conftest import ADMIN_PASSWORD


def test_login_returns_token_and_permissions(client, master_admin):
    response = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] is True
    assert body["data"]["access_token"]
    assert body["data"]["auth_key"]
    assert body["data"]["is_master"] is True
    # A master account is granted every permission without consulting grants.
    assert all(flag["status"] for flag in body["data"]["permissions"])
    assert response.headers["x-auth-key"] == body["data"]["auth_key"]


def test_login_accepts_login_name_as_well_as_email(client, master_admin):
    response = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.login_name, "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["status"] is True


def test_login_with_wrong_password_is_rejected(client, master_admin):
    response = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": "WrongPassword1#"},
    )

    assert response.status_code == 401
    assert response.json()["status"] is False


def test_login_does_not_reveal_whether_the_account_exists(client, master_admin):
    unknown = client.post(
        "/oan/admin/auth/login",
        json={"username": "nobody@example.org", "password": "WrongPassword1#"},
    )
    wrong_password = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": "WrongPassword1#"},
    )

    assert unknown.json()["message"] == wrong_password.json()["message"]


def test_protected_route_requires_both_headers(client, admin_headers):
    assert client.get("/oan/admin/auth/profile").status_code == 401

    assert (
        client.get(
            "/oan/admin/auth/profile",
            headers={"x-access-token": admin_headers["x-access-token"]},
        ).status_code
        == 401
    )

    assert (
        client.get("/oan/admin/auth/profile", headers=admin_headers).status_code == 200
    )


def test_logout_invalidates_the_session(client, admin_headers):
    assert (
        client.post("/oan/admin/auth/logout", headers=admin_headers).status_code == 200
    )

    # The JWT is still inside its lifetime, but the session handle is now dead.
    assert (
        client.get("/oan/admin/auth/profile", headers=admin_headers).status_code == 401
    )


def test_change_password_rejects_an_incorrect_current_password(client, admin_headers):
    response = client.post(
        "/oan/admin/auth/change-password",
        headers=admin_headers,
        json={"old_password": "NotThePassword1#", "new_password": "BrandNew1#"},
    )

    assert response.status_code == 400
    assert response.json()["status"] is False


def test_change_password_enforces_complexity(client, admin_headers):
    response = client.post(
        "/oan/admin/auth/change-password",
        headers=admin_headers,
        json={"old_password": ADMIN_PASSWORD, "new_password": "alllowercase"},
    )

    assert response.status_code == 400


def test_forgot_password_never_reveals_registration(client, master_admin):
    known = client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": master_admin.email_id}
    )
    unknown = client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": "nobody@example.org"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]
