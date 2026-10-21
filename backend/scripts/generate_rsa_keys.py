"""Create the RSA key pair used by the sealed login (``/auth/login/sealed``).

Writes ``RSA_PRIVATE_KEY_PATH`` and ``RSA_PUBLIC_KEY_PATH`` (default
``keys/private_key.pem`` and ``keys/public_key.pem``; ``keys/`` is git-ignored).
Give the public key to the web client, then set ``RSA_PAYLOAD_ENABLED=true``.

    python scripts/generate_rsa_keys.py            # refuses to overwrite
    python scripts/generate_rsa_keys.py --force    # replace an existing pair
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app.config.settings import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="overwrite an existing key pair")
    parser.add_argument("--bits", type=int, default=2048, choices=(2048, 3072, 4096))
    args = parser.parse_args()

    private_path = Path(settings.RSA_PRIVATE_KEY_PATH)
    public_path = Path(settings.RSA_PUBLIC_KEY_PATH)
    if private_path.exists() and not args.force:
        print(f"{private_path} already exists; use --force to replace it.")
        return 1

    key = rsa.generate_private_key(public_exponent=65537, key_size=args.bits)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Wrote {private_path} and {public_path} ({args.bits}-bit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
