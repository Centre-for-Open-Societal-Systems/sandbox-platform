"""Real keys and certificates for the tests (made once per run)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_pem(private_key) -> str:
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def private_pem(private_key) -> str:
    return private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def certificate(
    private_key=RSA_KEY,
    common_name: str = "partner.example.org",
    valid_from: datetime | None = None,
    valid_days: int = 365,
    issuer_key=None,
    der: bool = False,
) -> bytes:
    """An X.509 certificate for ``private_key``'s public key (self-signed unless ``issuer_key``)."""
    start = valid_from or datetime.now(UTC) - timedelta(days=1)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Partner Ltd"),
    ])
    issuer = subject if issuer_key is None else x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    signer = issuer_key or private_key
    algorithm = None if isinstance(signer, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(0x1A2B3C)
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=valid_days))
        .sign(signer, algorithm)
    )
    return cert.public_bytes(serialization.Encoding.DER if der else serialization.Encoding.PEM)


def ec_key(curve=None):
    return ec.generate_private_key(curve or ec.SECP256R1())


def ed25519_key():
    return ed25519.Ed25519PrivateKey.generate()
