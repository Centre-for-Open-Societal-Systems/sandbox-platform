"""Admin API usage & billing report (calls per partner / API / app / day / status)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest
from openpyxl import load_workbook

from app.core.permissions import Permission
from app.models.app import ParticipantApp
from app.models.catalog import Product
from app.models.logs import ApiLog
from app.models.participant import Participant
from app.utils import exporters
from tests.test_security_audit import _limited_admin

DAY = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def _partner(db, company, email, country="ET"):
    partner = Participant(
        first_name="P", last_name=company, email_id=email, company_name=company,
        country_code=country, is_email_verified=True,
    )
    db.add(partner)
    db.commit()
    return partner


@pytest.fixture
def usage_data(db_session):
    """Two Ethiopian partners and one Kenyan, with a known mix of outcomes."""
    db = db_session
    product = Product(product_name="farmer-registry", display_name="Farmer Registry")
    db.add(product)
    alpha = _partner(db, "Alpha Agri", "alpha@example.org")
    beta = _partner(db, "Beta Farms", "beta@example.org")
    kenya = _partner(db, "Kenya Co", "kenya@example.org", country="KE")
    db.commit()
    app = ParticipantApp(participant_id=alpha.participant_id, name="Alpha Mobile", environment="SANDBOX")
    db.add(app)
    db.commit()

    def log(partner, url, status, when=DAY, method="GET", source="TRYIT", app_id=None, latency=100.0):
        db.add(
            ApiLog(
                participant_id=partner.participant_id, country_code=partner.country_code,
                product_id=product.product_id, method=method, endpoint_url=url,
                status_code=status, source=source, app_id=app_id, environment="SANDBOX",
                latency_ms=latency, log_timestamp=when,
            )
        )

    # Alpha: 5 calls on /farmers (3 x 200, 1 x 404, 1 x 500), 2 on /farmers/{id} the next day.
    for status in (200, 200, 200, 404, 500):
        log(alpha, "/v1/farmers", status, source="DIRECT", app_id=app.app_id)
    log(alpha, "/v1/farmers/{id}", 200, when=DAY + timedelta(days=1))
    log(alpha, "/v1/farmers/{id}", None, when=DAY + timedelta(days=1))  # no answer -> server error
    # Beta: 2 calls, both 201.
    log(beta, "/v1/farmers", 201, method="POST", latency=300.0)
    log(beta, "/v1/farmers", 201, method="POST", latency=300.0)
    # Kenya: 1 call, only a master may see it.
    log(kenya, "/v1/farmers", 200)
    db.commit()
    return {"alpha": alpha, "beta": beta, "kenya": kenya, "app": app, "product": product}


def _usage(client, headers, **body):
    response = client.post("/oan/admin/logs/api-usage", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_usage_per_partner_counts_and_status_classes(client, admin_headers, usage_data):
    data = _usage(client, admin_headers, group_by="participant")
    rows = {row["participant_name"]: row for row in data["rows"]}

    assert data["pagination"]["total"] == 3
    assert data["rows"][0]["participant_name"] == "Alpha Agri"  # most calls first
    alpha = rows["Alpha Agri"]
    assert alpha["total_calls"] == 7
    assert alpha["success_calls"] == 4
    assert alpha["client_errors"] == 1
    assert alpha["server_errors"] == 2
    assert alpha["success_rate"] == pytest.approx(57.1)
    assert alpha["endpoints_used"] == 2
    assert alpha["apps_used"] == 1
    assert alpha["email_id"] == "alpha@example.org"
    beta = rows["Beta Farms"]
    assert (beta["total_calls"], beta["success_calls"], beta["avg_latency_ms"]) == (2, 2, 300.0)


def test_usage_partner_by_api_breakdown(client, admin_headers, usage_data):
    alpha = usage_data["alpha"]
    data = _usage(client, admin_headers, group_by="participant_endpoint", participant_id=alpha.participant_id)
    rows = {row["endpoint_url"]: row for row in data["rows"]}
    assert set(rows) == {"/v1/farmers", "/v1/farmers/{id}"}
    assert rows["/v1/farmers"]["total_calls"] == 5
    assert rows["/v1/farmers"]["product_name"] == "Farmer Registry"
    assert rows["/v1/farmers/{id}"]["server_errors"] == 1


@pytest.mark.parametrize(
    ("group_by", "expected"),
    [
        ("endpoint", {("GET", "/v1/farmers"): 6, ("GET", "/v1/farmers/{id}"): 2, ("POST", "/v1/farmers"): 2}),
        ("status", {200: 5, 201: 2, 404: 1, 500: 1, None: 1}),
        ("day", {"2026-10-20": 8, "2026-10-21": 2}),
        ("product", {"Farmer Registry": 10}),
    ],
)
def test_usage_other_groupings(client, admin_headers, usage_data, group_by, expected):
    rows = _usage(client, admin_headers, group_by=group_by, limit=50)["rows"]
    key = {
        "endpoint": lambda r: (r["method"], r["endpoint_url"]),
        "status": lambda r: r["status_code"],
        "day": lambda r: r["day"],
        "product": lambda r: r["product_name"],
    }[group_by]
    assert {key(row): row["total_calls"] for row in rows} == expected


def test_usage_per_app(client, admin_headers, usage_data):
    rows = _usage(client, admin_headers, group_by="app", source="DIRECT")["rows"]
    assert len(rows) == 1
    assert rows[0]["app_name"] == "Alpha Mobile"
    assert rows[0]["participant_name"] == "Alpha Agri"
    assert rows[0]["total_calls"] == 5


@pytest.mark.parametrize(
    ("filters", "total_calls"),
    [
        ({"status_class": "2xx"}, 7),
        ({"status_class": "4xx"}, 1),
        ({"status_class": "5xx"}, 2),
        ({"method": "post"}, 2),
        ({"source": "DIRECT"}, 5),
        ({"date_from": "2026-10-21", "date_to": "2026-10-21"}, 2),
        ({"date_to": "2026-10-20"}, 8),
        ({"country_code": "KE"}, 1),
        ({"search": "beta"}, 2),
        ({"search": "{id}"}, 2),
    ],
)
def test_usage_filters(client, admin_headers, usage_data, filters, total_calls):
    rows = _usage(client, admin_headers, group_by="participant", **filters)["rows"]
    assert sum(row["total_calls"] for row in rows) == total_calls


def test_usage_sort_and_paging(client, admin_headers, usage_data):
    data = _usage(client, admin_headers, group_by="participant", sort_by="total_calls", sort_dir="asc", limit=2)
    assert [row["total_calls"] for row in data["rows"]] == [1, 2]
    assert data["pagination"] == {"page": 1, "limit": 2, "total": 3, "total_pages": 2}
    page2 = _usage(client, admin_headers, group_by="participant", sort_by="total_calls", sort_dir="asc",
                   limit=2, page=2)
    assert [row["total_calls"] for row in page2["rows"]] == [7]
    # An unknown sort key falls back to total calls instead of failing.
    assert _usage(client, admin_headers, group_by="participant", sort_by="user_pass")["rows"][0]["total_calls"] == 7


def test_usage_rejects_unknown_grouping_and_status_class(client, admin_headers, usage_data):
    for body in ({"group_by": "drop table"}, {"status_class": "9xx"}):
        response = client.post("/oan/admin/logs/api-usage", json=body, headers=admin_headers)
        assert response.status_code == 400, response.text


def test_usage_summary(client, admin_headers, usage_data):
    response = client.post(
        "/oan/admin/logs/api-usage/summary",
        json={"date_from": "2026-10-19", "date_to": "2026-10-22"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["total_calls"] == 10
    assert (summary["success_calls"], summary["client_errors"], summary["server_errors"]) == (7, 1, 2)
    assert summary["success_rate"] == 70.0
    assert (summary["partners"], summary["apps"], summary["endpoints"]) == (3, 1, 2)
    assert {item["label"]: item["value"] for item in summary["by_status_code"]}["No answer"] == 1
    assert {item["label"]: item["value"] for item in summary["by_source"]} == {"DIRECT": 5, "TRYIT": 5}
    # Quiet days inside the range are zero-filled.
    assert [(p["label"], p["value"]) for p in summary["by_day"]] == [
        ("2026-10-19", 0), ("2026-10-20", 8), ("2026-10-21", 2), ("2026-10-22", 0),
    ]


def test_usage_options(client, admin_headers, usage_data):
    response = client.get("/oan/admin/logs/api-usage/options", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [p["name"] for p in data["products"]] == ["Farmer Registry"]
    # Partners and apps are too many to send whole: they come from the paged lookups.
    assert "partners" not in data


def _lookup(client, headers, kind, **body):
    response = client.post(f"/oan/admin/logs/api-usage/{kind}", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_partner_lookup_search_and_infinite_scroll(client, admin_headers, usage_data, db_session):
    # 45 more partners with calls, and one without (never offered).
    for index in range(45):
        partner = _partner(db_session, f"Gamma {index:02d}", f"gamma{index:02d}@example.org")
        db_session.add(ApiLog(participant_id=partner.participant_id, country_code="ET", status_code=200,
                              method="GET", endpoint_url="/v1/x", log_timestamp=DAY))
    _partner(db_session, "Silent Co", "silent@example.org")
    db_session.commit()

    seen, page = [], 1
    while True:
        data = _lookup(client, admin_headers, "partners", page=page, limit=20)
        seen += data["rows"]
        assert data["page"] == page
        if not data["has_more"]:
            break
        page += 1
    assert page == 3  # 48 partners in pages of 20
    assert len(seen) == 48 == len({row["id"] for row in seen})
    assert "Silent Co" not in {row["label"] for row in seen}
    assert seen[0] == {"id": usage_data["alpha"].participant_id, "label": "Alpha Agri", "hint": "alpha@example.org"}

    found = _lookup(client, admin_headers, "partners", search="GAMMA 1")
    assert [row["label"] for row in found["rows"]] == [f"Gamma {i}" for i in range(10, 20)]
    assert _lookup(client, admin_headers, "partners", search="beta@exa")["rows"][0]["label"] == "Beta Farms"
    assert _lookup(client, admin_headers, "partners", search="no such partner") == {
        "rows": [], "page": 1, "has_more": False,
    }


def test_app_lookup_filters_by_partner(client, admin_headers, usage_data):
    alpha, beta = usage_data["alpha"], usage_data["beta"]
    rows = _lookup(client, admin_headers, "apps")["rows"]
    assert rows == [{"id": usage_data["app"].app_id, "label": "Alpha Mobile", "hint": "Alpha Agri"}]
    assert _lookup(client, admin_headers, "apps", participant_ids=[beta.participant_id])["rows"] == []
    assert len(_lookup(client, admin_headers, "apps", participant_ids=[alpha.participant_id, beta.participant_id],
                       search="mobile")["rows"]) == 1


def test_lookup_validation(client, admin_headers, usage_data):
    for body in ({"limit": 51}, {"page": 0}, {"search": "x" * 101}):
        response = client.post("/oan/admin/logs/api-usage/partners", json=body, headers=admin_headers)
        assert response.status_code == 400, body


def test_multi_select_partner_and_app_filters(client, admin_headers, usage_data):
    alpha, beta, kenya = usage_data["alpha"], usage_data["beta"], usage_data["kenya"]
    rows = _usage(client, admin_headers, participant_ids=[alpha.participant_id, kenya.participant_id])["rows"]
    assert {row["participant_name"] for row in rows} == {"Alpha Agri", "Kenya Co"}
    assert sum(row["total_calls"] for row in rows) == 8

    summary = client.post("/oan/admin/logs/api-usage/summary",
                          json={"participant_ids": [beta.participant_id, kenya.participant_id]},
                          headers=admin_headers).json()["data"]
    assert summary["total_calls"] == 3
    assert _usage(client, admin_headers, app_ids=[usage_data["app"].app_id])["rows"][0]["total_calls"] == 5

    history = client.post("/oan/admin/logs/api-history",
                          json={"participant_ids": [beta.participant_id], "limit": 50},
                          headers=admin_headers).json()["data"]
    assert history["pagination"]["total"] == 2

    response = client.post(
        "/oan/admin/logs/api-usage/export",
        json={"format": "csv", "filters": {"participant_ids": [beta.participant_id]}},
        headers=admin_headers,
    )
    lines = response.content.decode("utf-8-sig").splitlines()
    assert len(lines) == 2 and "Beta Farms" in lines[1]


def test_usage_export_has_all_rows_and_columns(client, admin_headers, usage_data, db_session):
    # More rows than one grid page (200) must all reach the spreadsheet.
    partner = usage_data["beta"]
    for index in range(230):
        db_session.add(ApiLog(participant_id=partner.participant_id, country_code="ET", method="GET",
                              endpoint_url=f"/v1/x/{index}", status_code=200, log_timestamp=DAY))
    db_session.commit()

    response = client.post(
        "/oan/admin/logs/api-usage/export",
        json={"format": "xlsx", "filters": {"group_by": "endpoint", "page": 1, "limit": 10}},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert 'filename="api-usage-endpoint.xlsx"' in response.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(response.content)).active
    header = [cell.value for cell in sheet[1]]
    assert header[:3] == ["Product", "Method", "End-point"]
    assert "Total calls" in header and "Server errors (5xx / no answer)" in header
    assert sheet.max_row == 1 + 3 + 230

    csv_response = client.post(
        "/oan/admin/logs/api-usage/export",
        json={"format": "csv", "filters": {"group_by": "participant"}},
        headers=admin_headers,
    )
    assert csv_response.status_code == 200
    text = csv_response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Partner,Email,Country")
    assert "Alpha Agri" in text


def test_usage_needs_its_permission(client, db_session, usage_data):
    _, history_only = _limited_admin(db_session, client, [Permission.AUDIT_LOGS, Permission.API_HISTORY])
    assert client.post("/oan/admin/logs/api-usage", json={}, headers=history_only).status_code == 403
    # The filter lists also serve the API History screen.
    assert client.get("/oan/admin/logs/api-usage/options", headers=history_only).status_code == 200
    _, tracking_only = _limited_admin(
        db_session, client, [Permission.AUDIT_LOGS, Permission.USER_TRACKING], email="tracking@example.org"
    )
    assert client.get("/oan/admin/logs/api-usage/options", headers=tracking_only).status_code == 403
    assert client.post("/oan/admin/logs/api-usage/partners", json={}, headers=tracking_only).status_code == 403
    assert client.post("/oan/admin/logs/api-usage/apps", json={}, headers=tracking_only).status_code == 403
    assert client.post("/oan/admin/logs/api-usage/partners", json={}, headers=history_only).status_code == 200
    assert client.post("/oan/admin/logs/api-usage/export", json={}, headers=history_only).status_code == 403
    assert client.post("/oan/admin/logs/api-usage", json={}).status_code in (401, 403)


def test_country_admin_sees_only_own_country(client, db_session, usage_data):
    _, et_admin = _limited_admin(
        db_session, client, [Permission.AUDIT_LOGS, Permission.API_USAGE, Permission.API_HISTORY]
    )
    # Asking for Kenya does not widen the scope.
    rows = _usage(client, et_admin, group_by="participant", country_code="KE")["rows"]
    assert {row["participant_name"] for row in rows} == {"Alpha Agri", "Beta Farms"}

    summary = client.post("/oan/admin/logs/api-usage/summary", json={}, headers=et_admin).json()["data"]
    assert summary["total_calls"] == 9
    partners = _lookup(client, et_admin, "partners", limit=50)["rows"]
    assert {p["label"] for p in partners} == {"Alpha Agri", "Beta Farms"}
    assert _lookup(client, et_admin, "partners", search="kenya")["rows"] == []
    # Choosing a Kenyan partner by id still returns nothing outside the scope.
    assert _usage(client, et_admin, participant_ids=[usage_data["kenya"].participant_id])["rows"] == []

    history = client.post("/oan/admin/logs/api-history", json={"limit": 50}, headers=et_admin).json()["data"]
    assert history["pagination"]["total"] == 9
    kenya_log = next(
        log.id for log in db_session.query(ApiLog).filter(ApiLog.country_code == "KE")
    )
    assert client.get(f"/oan/admin/logs/api-history/{kenya_log}", headers=et_admin).status_code == 404


def test_api_history_shows_partner_name_and_exports_beyond_page_cap(client, admin_headers, usage_data, db_session):
    data = client.post("/oan/admin/logs/api-history", json={"source": "DIRECT"}, headers=admin_headers).json()["data"]
    assert {(log["participant_name"], log["app_name"]) for log in data["logs"]} == {("Alpha Agri", "Alpha Mobile")}
    filtered = client.post(
        "/oan/admin/logs/api-history", json={"status_class": "5xx", "limit": 50}, headers=admin_headers
    ).json()["data"]
    assert filtered["pagination"]["total"] == 2

    for _ in range(210):
        db_session.add(ApiLog(participant_id=usage_data["beta"].participant_id, country_code="ET",
                              method="GET", endpoint_url="/v1/bulk", status_code=200, log_timestamp=DAY))
    db_session.commit()
    response = client.post(
        "/oan/admin/logs/api-history/export", json={"format": "csv", "filters": {}}, headers=admin_headers
    )
    assert response.status_code == 200
    lines = response.content.decode("utf-8-sig").splitlines()
    assert len(lines) == 1 + 10 + 210
    assert "Partner" in lines[0].split(",")


def test_permission_catalogue_has_usage_screen():
    from app.core.permissions import PERMISSION_TREE

    assert PERMISSION_TREE[Permission.API_USAGE] == ("API Usage & Billing", Permission.AUDIT_LOGS, False)
    assert ("participant_name", "Partner") in exporters.API_LOG_COLUMNS
