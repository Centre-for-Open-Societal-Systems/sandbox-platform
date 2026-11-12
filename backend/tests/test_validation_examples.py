"""Validation messages say what format is expected and give a valid example."""

from __future__ import annotations

import pytest

from app.core.exceptions import _readable
from app.utils.validators import (
    COUNTRY_RULES,
    DEFAULT_RULES,
    normalise_msisdn,
    rules_for,
    validate_postal_code,
    validate_registration_number,
    validate_tin,
)

ALL_RULES = {**COUNTRY_RULES, "XX": DEFAULT_RULES}


@pytest.mark.parametrize("country", sorted(ALL_RULES))
def test_every_example_in_a_message_is_itself_valid(country):
    rules = ALL_RULES[country]
    code = "ZZ" if country == "XX" else country  # an unknown country gets DEFAULT_RULES
    if "registration" in rules.examples:
        validate_registration_number(rules.examples["registration"], code)
    if "tin" in rules.examples:
        validate_tin(rules.examples["tin"], code)
    if "postal" in rules.examples:
        validate_postal_code(rules.examples["postal"], code)
    if "mobile" in rules.examples:
        assert normalise_msisdn(rules.examples["mobile"], code) == f"+{rules.dial_code}{rules.examples['mobile']}"
        assert normalise_msisdn("0" + rules.examples["mobile"], code) == f"+{rules.dial_code}{rules.examples['mobile']}"


@pytest.mark.parametrize("country", sorted(COUNTRY_RULES))
def test_messages_give_the_format_and_an_example(country):
    rules = rules_for(country)
    with pytest.raises(ValueError) as registration:
        validate_registration_number("x", country)
    assert str(registration.value).startswith(f"{rules.labels['registration']} format is not valid. Use ")
    assert f"e.g. {rules.examples['registration']}." in str(registration.value)

    with pytest.raises(ValueError) as tin:
        validate_tin("x", country)
    assert f"e.g. {rules.examples['tin']}." in str(tin.value)

    with pytest.raises(ValueError) as mobile:
        normalise_msisdn("123", country)
    assert f"e.g. +{rules.dial_code}{rules.examples['mobile']} or 0{rules.examples['mobile']}." in str(mobile.value)


def test_ethiopian_messages_read_as_the_user_sees_them():
    with pytest.raises(ValueError, match=r"^Trade licence number format is not valid\. Use 6-20 letters, digits, / or -, "
                                         r"e\.g\. AA/1234/2015\.$"):
        validate_registration_number("x1", "ET")
    with pytest.raises(ValueError, match=r"^Postal code format is not valid\. Use 4 digits, e\.g\. 1000\.$"):
        validate_postal_code("12345", "ET")
    with pytest.raises(ValueError, match=r"e\.g\. \+12025550123\.$"):
        normalise_msisdn("123", "XX")


def test_api_shows_the_message_without_pydantics_prefix(client):
    from tests.test_participant_registration import SIGNUP_PAYLOAD

    response = client.post("/oan/participant/auth/signup", json={**SIGNUP_PAYLOAD, "mobile_number": "1234567"})
    assert response.status_code == 400
    assert response.json()["message"].startswith("Mobile number must be 9 digits after the country code (+251)")
    assert "Value error" not in response.text
    assert _readable("Value error, TIN format is not valid.") == "TIN format is not valid."
    assert _readable("Assertion failed, nope") == "nope"
    assert _readable("Field required") == "Field required"
