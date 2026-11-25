"""Console editing of email templates: edit, preview with sample values, test mail."""

from __future__ import annotations

from app.models.content import EmailTemplate


def _template(client, db_session, admin_headers, code="PROMOTION_APPROVED") -> EmailTemplate:
    created = client.post("/oan/admin/email-templates", headers=admin_headers, json={
        "template_code": code, "template_name": "Environment access approved",
        "subject": "{{environment}} access approved", "body_text": "<p>Dear {{name}}</p>"})
    assert created.status_code == 200, created.text
    return db_session.query(EmailTemplate).filter_by(template_code=code, locale="en").one()


def test_edit_changes_the_design_but_never_the_code_or_locale(client, db_session, admin_headers):
    row = _template(client, db_session, admin_headers)
    saved = client.post("/oan/admin/email-templates", headers=admin_headers, json={
        "template_id": row.template_id,
        "template_code": "SOMETHING_ELSE",
        "template_name": "Environment access approved",
        "subject": "{{environment}} is open for {{name}}",
        "body_text": '<div style="color:#14532d"><h1>Welcome</h1><p>Dear {{name}}, see {{portal_url}}</p></div>',
        "locale": "fr",
        "variables": ["stale"],
    })
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert (data["template_code"], data["locale"]) == ("PROMOTION_APPROVED", "en")
    assert data["variables"] == ["environment", "name", "portal_url"]  # follows the saved text
    db_session.refresh(row)
    assert row.body_text.startswith('<div style="color:#14532d">')


def test_preview_fills_placeholders_with_sample_values(client, admin_headers):
    response = client.post("/oan/admin/email-templates/preview", headers=admin_headers, json={
        "subject": "Code {{otp}}",
        "body_text": "<p>Dear {{name}}, {{environment}} {{custom_field}} {{portal_url}}</p>",
    })
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["subject"] == "Code 482915"
    assert "Dear Abebe Kebede, UAT [custom_field] http" in data["body_html"]
    assert data["placeholders"] == ["custom_field", "environment", "name", "otp", "portal_url"]


def test_preview_and_test_mail_need_the_cms_permission(client):
    assert client.post("/oan/admin/email-templates/preview", json={"subject": "x", "body_text": "y"}).status_code == 401


def test_test_mail_sends_the_stored_template_with_every_placeholder_filled(
    client, admin_headers, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "app.services.notification_service.send_email",
        lambda to, subject, body: sent.append((to, subject, body)) or True,
    )
    response = client.post("/oan/admin/email-templates/test", headers=admin_headers,
                           json={"to_email": "qa@example.org", "template_code": "PROMOTION_REJECTED"})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"sent": True}
    [(to, subject, body)] = sent
    assert to == "qa@example.org" and subject == "UAT access request declined"
    assert "{{" not in body and "could not be verified" in body
