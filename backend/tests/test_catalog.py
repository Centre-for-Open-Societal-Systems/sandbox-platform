"""API catalogue administration and the public catalogue view."""

from __future__ import annotations

import json

from app.models.catalog import Endpoint, EndpointSchema

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Farmer Registry", "version": "1.2.0"},
    "paths": {
        "/farmers/{farmerId}": {
            "get": {
                "summary": "Fetch a farmer record",
                "parameters": [
                    {
                        "name": "farmerId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Farmer record",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Farmer"}
                            }
                        },
                    }
                },
            }
        },
        "/farmers/search": {
            "post": {
                "summary": "Search farmers",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "region": {"type": "string"},
                                    "limit": {"type": "integer"},
                                },
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "Matches"}},
            }
        },
    },
    "components": {
        "schemas": {
            "Farmer": {
                "type": "object",
                "properties": {
                    "farmerId": {"type": "string"},
                    "fullName": {"type": "string"},
                    "region": {"type": "string"},
                },
            }
        }
    },
}


def _create_product(client, admin_headers, name="Farmer Registry"):
    response = client.post(
        "/oan/admin/products",
        headers=admin_headers,
        json={"product_name": name, "description": "Farmer identity APIs."},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_product(client, admin_headers):
    product = _create_product(client, admin_headers)

    assert product["product_id"]
    assert product["is_published"] is False
    assert product["endpoint_count"] == 0


def test_product_names_must_be_unique(client, admin_headers):
    _create_product(client, admin_headers)

    response = client.post(
        "/oan/admin/products",
        headers=admin_headers,
        json={"product_name": "Farmer Registry"},
    )

    assert response.status_code == 409


def test_product_cannot_be_published_without_endpoints(client, admin_headers):
    product = _create_product(client, admin_headers)

    response = client.post(
        "/oan/admin/products/publish",
        headers=admin_headers,
        json={"id": product["product_id"], "is_published": True},
    )

    assert response.status_code == 400
    assert "endpoint" in response.json()["message"].lower()


def test_spec_import_creates_endpoints_and_schemas(client, admin_headers, db_session):
    product = _create_product(client, admin_headers)

    response = client.post(
        "/oan/admin/products/import-spec",
        headers=admin_headers,
        json={
            "product_id": product["product_id"],
            "spec_text": json.dumps(OPENAPI_SPEC),
            "replace_existing": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"created": 2, "updated": 0, "total": 2}

    endpoints = {e.endpoint_url: e for e in db_session.query(Endpoint).all()}
    assert set(endpoints) == {"/farmers/{farmerId}", "/farmers/search"}
    assert endpoints["/farmers/{farmerId}"].method == "GET"
    assert endpoints["/farmers/search"].method == "POST"
    assert endpoints["/farmers/{farmerId}"].path_params["farmerId"]["required"] is True

    # $ref pointers are inlined so a stored schema is self-contained.
    schema = (
        db_session.query(EndpointSchema)
        .filter_by(endpoint_id=endpoints["/farmers/{farmerId}"].endpoint_id)
        .one()
    )
    assert schema.res_schema["properties"]["fullName"] == {"type": "string"}
    assert schema.res_json == {
        "farmerId": "string",
        "fullName": "string",
        "region": "string",
    }


def test_re_importing_a_spec_updates_rather_than_duplicates(
    client, admin_headers, db_session
):
    product = _create_product(client, admin_headers)
    payload = {
        "product_id": product["product_id"],
        "spec_text": json.dumps(OPENAPI_SPEC),
        "replace_existing": False,
    }

    client.post("/oan/admin/products/import-spec", headers=admin_headers, json=payload)
    response = client.post(
        "/oan/admin/products/import-spec", headers=admin_headers, json=payload
    )

    assert response.json()["data"] == {"created": 0, "updated": 2, "total": 2}
    assert db_session.query(Endpoint).count() == 2


def test_spec_import_rejects_malformed_input(client, admin_headers):
    product = _create_product(client, admin_headers)

    response = client.post(
        "/oan/admin/products/import-spec",
        headers=admin_headers,
        json={"product_id": product["product_id"], "spec_text": "not-a-spec: ["},
    )

    assert response.status_code == 400


def test_duplicate_endpoint_route_is_rejected(client, admin_headers):
    product = _create_product(client, admin_headers)
    payload = {
        "product_id": product["product_id"],
        "display_name": "Fetch farmer",
        "endpoint_url": "/farmers/{farmerId}",
        "method": "GET",
    }

    assert (
        client.post(
            "/oan/admin/endpoints", headers=admin_headers, json=payload
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/oan/admin/endpoints", headers=admin_headers, json=payload
        ).status_code
        == 409
    )


def test_public_catalogue_only_lists_published_products(client, admin_headers):
    product = _create_product(client, admin_headers)
    client.post(
        "/oan/admin/endpoints",
        headers=admin_headers,
        json={
            "product_id": product["product_id"],
            "display_name": "Fetch farmer",
            "endpoint_url": "/farmers/{farmerId}",
            "method": "GET",
        },
    )

    assert client.get("/oan/catalog/products").json()["data"] == []

    client.post(
        "/oan/admin/products/publish",
        headers=admin_headers,
        json={"id": product["product_id"], "is_published": True},
    )

    listed = client.get("/oan/catalog/products").json()["data"]
    assert [item["product_name"] for item in listed] == ["Farmer Registry"]


def test_schema_generation_from_a_sample(client, admin_headers):
    response = client.post(
        "/oan/admin/schemas/generate",
        headers=admin_headers,
        json={
            "sample": {
                "farmerId": "ET-0001",
                "registeredOn": "2026-01-15",
                "hectares": 2.5,
                "active": True,
                "parcels": [{"parcelId": "P1"}],
            }
        },
    )

    schema = response.json()["data"]
    assert schema["type"] == "object"
    assert schema["properties"]["hectares"]["type"] == "number"
    assert schema["properties"]["active"]["type"] == "boolean"
    assert schema["properties"]["registeredOn"]["format"] == "date"
    assert schema["properties"]["parcels"]["items"]["type"] == "object"


def test_curl_conversion(client, participant_headers):
    response = client.post(
        "/oan/participant/curl-convert",
        headers=participant_headers,
        json={
            "curl_command": (
                "curl -X POST 'https://api.example.org/farmers/search?page=2' "
                "-H 'Content-Type: application/json' "
                '-d \'{"region":"Oromia"}\''
            )
        },
    )

    data = response.json()["data"]
    assert data["method"] == "POST"
    assert data["path"] == "/farmers/search"
    assert data["query_params"] == {"page": "2"}
    assert data["headers"]["Content-Type"] == "application/json"
    assert data["body"] == {"region": "Oromia"}


def test_catalogue_requires_authentication(client):
    assert (
        client.post("/oan/admin/products", json={"product_name": "X"}).status_code
        == 401
    )


def test_product_categories_can_be_created_and_listed(client, admin_headers):
    response = client.post(
        "/oan/admin/product-categories",
        headers=admin_headers,
        data={"category_name": "Credit", "description": "Loan APIs"},
    )
    assert response.status_code == 200, response.text

    listed = client.post(
        "/oan/admin/product-categories/list", headers=admin_headers, json={"page": 1}
    )
    assert listed.status_code == 200, listed.text
    names = [row["category_name"] for row in listed.json()["data"]["categories"]]
    assert "Credit" in names


def test_product_category_update_keeps_unsent_fields(client, admin_headers):
    created = client.post(
        "/oan/admin/product-categories",
        headers=admin_headers,
        data={"category_name": "Credit", "description": "Loan APIs", "icon_path": "categories/x.png"},
    ).json()["data"]

    response = client.put(
        "/oan/admin/product-categories",
        headers=admin_headers,
        data={"category_id": created["category_id"], "category_name": "Credit APIs"},
    )

    assert response.status_code == 200, response.text
    row = response.json()["data"]
    assert row["category_name"] == "Credit APIs"
    assert row["description"] == "Loan APIs"
    assert row["icon_path"]
