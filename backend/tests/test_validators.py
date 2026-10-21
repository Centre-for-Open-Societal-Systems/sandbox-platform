"""Per-country field validation and the code-sample generator."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.utils import schema_tools
from app.utils.validators import (
    normalise_msisdn,
    validate_password_strength,
    validate_registration_number,
    validate_tin,
)


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("0911234567", "+251911234567"),
        ("911234567", "+251911234567"),
        ("+251911234567", "+251911234567"),
        ("251911234567", "+251911234567"),
        ("091 123 4567", "+251911234567"),
    ],
)
def test_ethiopian_mobile_numbers_normalise_to_e164(supplied, expected):
    assert normalise_msisdn(supplied, "ET") == expected


@pytest.mark.parametrize("supplied", ["12345", "09112345678901", ""])
def test_malformed_ethiopian_mobile_numbers_are_rejected(supplied):
    with pytest.raises(ValueError):
        normalise_msisdn(supplied, "ET")


def test_mobile_rules_differ_per_country():
    assert normalise_msisdn("0712345678", "KE") == "+254712345678"
    assert normalise_msisdn("08012345678", "NG") == "+2348012345678"


def test_unknown_country_falls_back_to_a_permissive_rule():
    assert normalise_msisdn("+441234567890", "XX") == "+441234567890"


def test_tax_id_format_is_country_specific():
    assert validate_tin("0012345678", "ET") == "0012345678"

    with pytest.raises(ValueError):
        validate_tin("ABC", "ET")

    # Kenya's KRA PIN has a different shape entirely.
    assert validate_tin("A123456789Z", "KE") == "A123456789Z"


def test_registration_number_is_upper_cased_and_checked():
    assert validate_registration_number("et/aa/1234", "ET") == "ET/AA/1234"

    with pytest.raises(ValueError):
        validate_registration_number("!!", "ET")


@pytest.mark.parametrize(
    "weak",
    ["short1#", "alllowercase1#", "ALLUPPERCASE1#", "NoDigitsHere#", "NoSymbols123"],
)
def test_weak_passwords_are_rejected(weak):
    with pytest.raises(ValueError):
        validate_password_strength(weak)


def test_a_strong_password_is_accepted():
    assert validate_password_strength("Str0ng#Pass") == "Str0ng#Pass"


def test_schema_inference_detects_types_and_formats():
    schema = schema_tools.infer_schema(
        {
            "farmerId": "ET-0001",
            "registeredOn": "2026-01-15",
            "contact": "farmer@example.et",
            "hectares": 2.5,
            "active": True,
            "parcels": [{"parcelId": "P1"}],
        }
    )

    properties = schema["properties"]
    assert properties["hectares"]["type"] == "number"
    assert properties["active"]["type"] == "boolean"
    assert properties["registeredOn"]["format"] == "date"
    assert properties["contact"]["format"] == "email"
    assert properties["parcels"]["items"]["properties"]["parcelId"]["type"] == "string"


def test_array_of_differing_objects_only_requires_shared_keys():
    schema = schema_tools.infer_schema([{"a": 1, "b": 2}, {"a": 3}])

    assert schema["type"] == "array"
    assert schema["items"]["required"] == ["a"]


def test_curl_parsing_extracts_every_part():
    parsed = schema_tools.parse_curl(
        "curl -X POST 'https://api.example.org/farmers/search?page=2' "
        "-H 'Content-Type: application/json' "
        '-d \'{"region":"Oromia"}\''
    )

    assert parsed["method"] == "POST"
    assert parsed["path"] == "/farmers/search"
    assert parsed["query_params"] == {"page": "2"}
    assert parsed["headers"]["Content-Type"] == "application/json"
    assert parsed["body"] == {"region": "Oromia"}


def test_curl_parsing_infers_get_when_no_body_is_present():
    parsed = schema_tools.parse_curl("curl https://api.example.org/farmers/ET-0001")

    assert parsed["method"] == "GET"
    assert parsed["body"] is None


def test_curl_parsing_rejects_a_non_curl_command():
    with pytest.raises(ValidationError):
        schema_tools.parse_curl("wget https://api.example.org")


@pytest.mark.parametrize(
    "language", ["curl", "python", "javascript", "java", "go", "php", "csharp"]
)
def test_every_supported_language_produces_a_snippet(language):
    code = schema_tools.build_code_sample(
        language,
        "POST",
        "https://api.example.org/farmers/search",
        {"Content-Type": "application/json"},
        {"region": "Oromia"},
    )

    assert code.strip()
    assert "farmers/search" in code


# ------------------------------------------- OpenAPI import: allOf / shared responses
ENVELOPE_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Envelope", "version": "1"},
    "paths": {
        "/v1/me": {
            "get": {
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Envelope"},
                                        {
                                            "type": "object",
                                            "properties": {
                                                "data": {"$ref": "#/components/schemas/User"}
                                            },
                                        },
                                    ]
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Envelope": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "success"},
                    "data": {"type": "object", "properties": {}},
                },
                "required": ["status"],
            },
            "User": {"type": "object", "properties": {"email": {"type": "string"}}},
        },
        "responses": {
            "Unauthorized": {
                "description": "No token",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"status": {"type": "string", "example": "error"}},
                        }
                    }
                },
            }
        },
    },
}


def test_import_merges_allof_envelopes_into_one_sample():
    from app.utils import schema_tools

    [operation] = schema_tools.endpoints_from_spec(ENVELOPE_SPEC)
    ok = next(r for r in operation["responses"] if r["status_code"] == "200")

    assert ok["res_json"] == {"status": "success", "data": {"email": "string"}}
    assert ok["res_schema"]["required"] == ["status"]
    assert "allOf" not in ok["res_schema"]


def test_import_resolves_shared_component_responses():
    from app.utils import schema_tools

    [operation] = schema_tools.endpoints_from_spec(ENVELOPE_SPEC)
    unauthorized = next(r for r in operation["responses"] if r["status_code"] == "401")

    assert unauthorized["description"] == "No token"
    assert unauthorized["res_json"] == {"status": "error"}
