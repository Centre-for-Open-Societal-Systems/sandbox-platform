"""Give the two Beneficiary Portal endpoints realistic request/200-response samples."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.catalog import Endpoint, EndpointSchema  # noqa: E402


def header(request_id: str) -> dict:
    return {
        "sender_app_mnemonic": "oan-sandbox",
        "sender_app_url": "http://localhost:3004",
        "request_id": request_id,
        "request_timestamp": "2026-09-29T10:00:00Z",
        "instance_id": None,
    }


def response_header(request_id: str) -> dict:
    return {
        "request_id": request_id,
        "response_status": "SUCCESS",
        "response_error_code": None,
        "response_error_message": None,
        "response_timestamp": "2026-09-29T10:00:01Z",
    }


FARMER = {
    "register_id": "5f1c2a9e-3b7d-4c21-9a55-0d6e8b1f4a10",
    "register_mnemonic": "farmer",
    "register_subject": "Farmer",
    "register_description": "Farmers registered with the Ministry of Agriculture",
    "master_register_id": None,
    "register_purpose": "Identify farmers eligible for agricultural programmes",
    "register_rank": 1,
    "register_icon": "agriculture",
    "functional_id_generation_required": True,
    "completion_score_required": True,
}
FARM_PLOT = {
    **FARMER,
    "register_id": "8a4d7e21-6c90-4f3b-b812-2e5f9c7d3b64",
    "register_mnemonic": "farm_plot",
    "register_subject": "Farm plot",
    "register_description": "Land parcels cultivated by a registered farmer",
    "master_register_id": FARMER["register_id"],
    "register_purpose": "Record the plots each farmer cultivates",
    "register_rank": 2,
    "register_icon": "landscape",
    "functional_id_generation_required": False,
}

SAMPLES = {
    "/beneficiary_portal/get_all_registers": {
        "request": {
            "request_header": header("REQ-0001"),
            "request_body": {
                "request_payload": {},
                "pagination_request": {"current_page": 1, "page_size": 10},
            },
        },
        "response": {
            "response_header": response_header("REQ-0001"),
            "response_body": {
                "pagination_response": {"number_of_items": 2, "number_of_pages": 1},
                "response_payload": [
                    {
                        **FARMER,
                        "master_register_mnemonic": None,
                        "has_data": True,
                        "program_id": None,
                        "program_mnemonic": None,
                        "has_image": True,
                    },
                    {
                        **FARM_PLOT,
                        "master_register_mnemonic": "farmer",
                        "has_data": False,
                        "program_id": None,
                        "program_mnemonic": None,
                        "has_image": False,
                    },
                ],
            },
        },
    },
    "/beneficiary_portal/get_register": {
        "request": {
            "request_header": header("REQ-0002"),
            "request_body": {
                "request_payload": {"register_id": FARMER["register_id"]},
                "pagination_request": None,
            },
        },
        "response": {
            "response_header": response_header("REQ-0002"),
            "response_body": {"pagination_response": None, "response_payload": FARMER},
        },
    },
}

ERRORS = {
    "401": ("G2P-AUT-401", "Beneficiary is not logged in or the session has expired."),
    "403": ("G2P-AUT-403", "Beneficiary is not allowed to view this register."),
    "404": ("G2P-REG-404", "Register not found."),
    "500": ("G2P-SYS-500", "Unexpected error while reading the registry."),
}

db = SessionLocal()
for path, sample in SAMPLES.items():
    endpoint = db.execute(
        select(Endpoint).where(Endpoint.endpoint_url == path, Endpoint.is_deleted.is_(False))
    ).scalars().first()
    endpoint.request_sample = sample["request"]
    for row in db.execute(
        select(EndpointSchema).where(EndpointSchema.endpoint_id == endpoint.endpoint_id)
    ).scalars():
        row.req_json = sample["request"]
        if row.status_code == "200":
            row.res_json = sample["response"]
        elif row.status_code in ERRORS:
            code, message = ERRORS[row.status_code]
            row.res_json = {"errors": [{"code": code, "message": message}]}
        elif row.status_code == "422":
            row.res_json = {
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "request_header", "request_id"],
                        "msg": "Field required",
                        "input": None,
                    }
                ]
            }
    print("updated", endpoint.endpoint_id, path)
db.commit()
db.close()
