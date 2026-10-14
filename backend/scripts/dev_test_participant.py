"""Create (or reset) a local test participant with sandbox access, for trying the portal.

Local development only - never run against a shared or production database.

    venv\\Scripts\\python.exe scripts\\dev_test_participant.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.participant import Participant  # noqa: E402

EMAIL = "sandbox.tester@example.test"
PASSWORD = "Sandbox#Tester2026"


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(Participant).filter(Participant.email_id == EMAIL).one_or_none()
        if user is None:
            user = Participant(
                first_name="Sandbox",
                last_name="Tester",
                email_id=EMAIL,
                mobile_number="+251900000000",
                company_name="Local Test Org",
                category_id=1,
                country_code="ET",
                declaration=True,
            )
            db.add(user)
        user.user_pass = hash_password(PASSWORD)
        user.is_email_verified = True
        user.is_approved = 1
        user.is_activated = 1
        user.is_sandbox_approved = True
        db.commit()
        print(f"Test participant ready: {EMAIL} (password in this script)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
