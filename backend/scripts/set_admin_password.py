"""Set an administrator's password from the server, when mail is not available.

Administrators have no code-based reset (anyone could use a shared code), so
an operator with shell access to the API sets it here. Every session of the
account is signed out.

    venv\Scripts\python.exe scripts\set_admin_password.py admin@openagrinet.org
    docker exec -it oan-sandbox-api-1 python scripts/set_admin_password.py admin@openagrinet.org
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.repositories.admin_repository import (  # noqa: E402
    AdminTokenRepository,
    AdminUserRepository,
)
from app.utils.validators import validate_password_strength  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    email = sys.argv[1].strip().lower()
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat it: "):
        print("The passwords do not match.")
        return 1
    try:
        validate_password_strength(password)
    except ValueError as exc:
        print(exc)
        return 1

    db = SessionLocal()
    try:
        user = AdminUserRepository(db).get_by(email_id=email)
        if user is None:
            print(f"No administrator with the address {email}.")
            return 1
        user.login_pass = hash_password(password)
        user.set_pass_token = None
        user.set_pass_token_time = None
        user.is_activated = True
        db.commit()
        AdminTokenRepository(db).logout_all(user.admin_id)
        print(f"Password set for {email}; existing sessions signed out.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
