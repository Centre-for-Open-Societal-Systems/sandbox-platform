"""The partner's signing key: certificate or public key, checked the standard way."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.core.exceptions import ValidationError
from app.services.partner_portal_service import _jwk
from app.utils.partner_keys import partner_key
from tests.keys import (
    RSA_KEY,
    certificate,
    ec_key,
    ed25519_key,
    private_pem,
    public_pem,
)


def test_the_key_is_read_from_the_certificate():
    key = partner_key(certificate(), None)

    assert key.source == "certificate"
    assert key.algorithm == "RSA 2048"
    assert key.public_key == public_pem(RSA_KEY).strip()
    der = RSA_KEY.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert key.fingerprint_sha256.replace(":", "") == hashlib.sha256(der).hexdigest().upper()
    assert key.certificate.common_name == "partner.example.org"
    assert key.certificate.self_signed is True
    assert key.certificate.serial_number == "1A2B3C"
    assert "details" not in key.details() and "public_key" not in key.details()
    assert _jwk(key.public_key) is not None  # the partner JWKS can publish it


def test_a_der_certificate_and_one_signed_by_a_ca_are_read():
    assert partner_key(certificate(der=True), None).algorithm == "RSA 2048"
    ca_signed = partner_key(certificate(issuer_key=ec_key()), None)
    assert ca_signed.certificate.self_signed is False
    assert ca_signed.certificate.issuer == "CN=Test CA"


def test_a_pasted_public_key_alone_is_enough():
    key = partner_key(None, public_pem(RSA_KEY))
    assert key.source == "public_key" and key.certificate is None and key.algorithm == "RSA 2048"


def test_certificate_and_public_key_must_hold_the_same_key():
    assert partner_key(certificate(), public_pem(RSA_KEY)).source == "certificate"
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValidationError, match="does not match the certificate"):
        partner_key(certificate(), public_pem(other))


@pytest.mark.parametrize(
    ("private_key", "algorithm"),
    [(ec_key(), "EC P-256"), (ec_key(ec.SECP384R1()), "EC P-384"), (ed25519_key(), "Ed25519")],
)
def test_ec_and_ed25519_keys_are_accepted(private_key, algorithm):
    assert partner_key(certificate(private_key), None).algorithm == algorithm
    assert partner_key(None, public_pem(private_key)).algorithm == algorithm


def test_weak_or_unusual_keys_are_refused():
    small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    with pytest.raises(ValidationError, match="1024 bits; at least 2048"):
        partner_key(None, public_pem(small))
    with pytest.raises(ValidationError, match="secp521r1 is not accepted"):
        partner_key(None, public_pem(ec_key(ec.SECP521R1())))


def test_expired_and_not_yet_valid_certificates_are_refused():
    old = datetime.now(UTC) - timedelta(days=400)
    with pytest.raises(ValidationError, match=r"expired on \d{4}-\d{2}-\d{2}"):
        partner_key(certificate(valid_from=old, valid_days=30), None)
    with pytest.raises(ValidationError, match="not valid before"):
        partner_key(certificate(valid_from=datetime.now(UTC) + timedelta(days=10)), None)


def test_private_keys_are_never_taken():
    with pytest.raises(ValidationError, match="This is a private key"):
        partner_key(None, private_pem(RSA_KEY))
    with pytest.raises(ValidationError, match="This is a private key"):
        partner_key(private_pem(RSA_KEY).encode(), None)


def test_unreadable_input_says_what_is_expected():
    with pytest.raises(ValidationError, match="Upload your certificate"):
        partner_key(None, "  ")
    with pytest.raises(ValidationError, match="public key could not be read"):
        partner_key(None, "-----BEGIN PUBLIC KEY-----abc-----END PUBLIC KEY-----")
    with pytest.raises(ValidationError, match="certificate could not be read"):
        partner_key(b"-----BEGIN CERTIFICATE-----", None)
    with pytest.raises(ValidationError, match="certificate could not be read"):
        partner_key(b"not a certificate", None)
    with pytest.raises(ValidationError, match="This is a certificate, not a public key"):
        partner_key(None, certificate().decode())
