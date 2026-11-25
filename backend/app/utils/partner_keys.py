"""A partner's signing key, from its X.509 certificate or its public key.

The certificate carries the public key, so a partner sends one of them: the
certificate (preferred: it also says whose key it is and until when) or, without
one, the public key itself. When both come they must hold the same key.

Accepted, as the partner JWKS (``partner_portal_service``) publishes them: RSA of
2048 bits or more, EC P-256 / P-384, Ed25519. A private key is always refused.
The key is kept as a PEM ``SubjectPublicKeyInfo``; its fingerprint is the
SHA-256 of that structure's DER (what ``openssl pkey -pubin -outform DER |
sha256sum`` prints).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from app.core.exceptions import ValidationError

#: Certificate files the field takes (PEM or DER).
CERTIFICATE_EXTENSIONS = {"pem", "crt", "cer", "der"}

_EC_CURVES = {"secp256r1": "P-256", "secp384r1": "P-384"}
_ACCEPTED = "an RSA key of 2048 bits or more, an EC P-256 / P-384 key or an Ed25519 key"

PRIVATE_KEY_MESSAGE = (
    "This is a private key. Never share it: upload your certificate, or paste the public key "
    "(openssl pkey -in private.pem -pubout)."
)
MISSING_MESSAGE = (
    "Upload your certificate (.pem, .crt, .cer or .der) or paste your public key "
    "(-----BEGIN PUBLIC KEY-----)."
)


@dataclass(frozen=True, slots=True)
class CertificateInfo:
    subject: str
    common_name: str | None
    issuer: str
    serial_number: str
    not_before: str
    not_after: str
    self_signed: bool


@dataclass(frozen=True, slots=True)
class PartnerKey:
    #: PEM SubjectPublicKeyInfo ("-----BEGIN PUBLIC KEY-----").
    public_key: str
    #: e.g. "RSA 2048", "EC P-256", "Ed25519".
    algorithm: str
    #: SHA-256 of the key's DER, upper-case hex pairs joined by ":".
    fingerprint_sha256: str
    #: Where the key was read from: "certificate" or "public_key".
    source: str
    certificate: CertificateInfo | None = None

    def details(self) -> dict[str, Any]:
        """What is kept with the request (everything but the PEM itself)."""
        data = asdict(self)
        data.pop("public_key")
        return data


def partner_key(
    certificate: bytes | None, public_key: str | None, now: datetime | None = None
) -> PartnerKey:
    """The partner's key from ``certificate`` (file contents) and / or ``public_key``
    (pasted PEM). Raises :class:`ValidationError` with what to fix."""
    pasted = (public_key or "").strip()
    if not certificate and not pasted:
        raise ValidationError(MISSING_MESSAGE)
    pasted_key = _load_public_key(pasted) if pasted else None
    if not certificate:
        assert pasted_key is not None
        return _describe(pasted_key, "public_key")

    cert = _load_certificate(certificate)
    _check_validity(cert, now or datetime.now(UTC))
    cert_key = cert.public_key()
    if pasted_key is not None and _der(pasted_key) != _der(cert_key):
        raise ValidationError(
            "The public key does not match the certificate. Leave the public key empty (it is read from "
            "the certificate), or paste the certificate's key (openssl x509 -in certificate.crt -pubkey -noout)."
        )
    return _describe(cert_key, "certificate", _certificate_info(cert))


# ------------------------------------------------------------------ reading
def _load_public_key(text: str):
    if "PRIVATE KEY" in text:
        raise ValidationError(PRIVATE_KEY_MESSAGE)
    if "BEGIN CERTIFICATE" in text:
        raise ValidationError(
            "This is a certificate, not a public key. Upload it as the certificate file instead."
        )
    try:
        return serialization.load_pem_public_key(text.encode())
    except (ValueError, TypeError, UnicodeError):
        raise ValidationError(
            "The public key could not be read. Paste a PEM public key, from -----BEGIN PUBLIC KEY----- "
            "to -----END PUBLIC KEY-----."
        ) from None


def _load_certificate(data: bytes) -> x509.Certificate:
    if b"PRIVATE KEY" in data:
        raise ValidationError(PRIVATE_KEY_MESSAGE)
    try:
        if b"-----BEGIN" in data:
            return x509.load_pem_x509_certificate(data)
        return x509.load_der_x509_certificate(data)
    except ValueError:
        raise ValidationError(
            "The certificate could not be read. Upload an X.509 certificate, in PEM "
            "(-----BEGIN CERTIFICATE-----) or DER form."
        ) from None


def _check_validity(cert: x509.Certificate, now: datetime) -> None:
    if now > cert.not_valid_after_utc:
        raise ValidationError(
            f"The certificate expired on {cert.not_valid_after_utc:%Y-%m-%d}. Upload a certificate that is still valid."
        )
    if now < cert.not_valid_before_utc:
        raise ValidationError(f"The certificate is not valid before {cert.not_valid_before_utc:%Y-%m-%d}.")


# ---------------------------------------------------------------- describing
def _algorithm(key) -> str:
    if isinstance(key, rsa.RSAPublicKey):
        if key.key_size < 2048:
            raise ValidationError(
                f"The RSA key has {key.key_size} bits; at least 2048 are needed. Use {_ACCEPTED}."
            )
        return f"RSA {key.key_size}"
    if isinstance(key, ec.EllipticCurvePublicKey):
        curve = _EC_CURVES.get(key.curve.name)
        if curve is None:
            raise ValidationError(f"The EC curve {key.curve.name} is not accepted. Use {_ACCEPTED}.")
        return f"EC {curve}"
    if isinstance(key, ed25519.Ed25519PublicKey):
        return "Ed25519"
    raise ValidationError(f"This key type is not accepted. Use {_ACCEPTED}.")


def _der(key) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def fingerprint(key) -> str:
    digest = hashlib.sha256(_der(key)).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def _describe(key, source: str, certificate: CertificateInfo | None = None) -> PartnerKey:
    algorithm = _algorithm(key)
    pem = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return PartnerKey(
        public_key=pem.decode().strip(),
        algorithm=algorithm,
        fingerprint_sha256=fingerprint(key),
        source=source,
        certificate=certificate,
    )


def _certificate_info(cert: x509.Certificate) -> CertificateInfo:
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return CertificateInfo(
        subject=cert.subject.rfc4514_string(),
        common_name=str(names[0].value) if names else None,
        issuer=cert.issuer.rfc4514_string(),
        serial_number=format(cert.serial_number, "X"),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        self_signed=cert.issuer == cert.subject,
    )
