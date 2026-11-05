"""Create Keycloak users for participants approved before provisioning was on.

Participants approved while KEYCLOAK_PROVISIONING_ENABLED was off (or before
26 Oct 2026) have no Keycloak user. This lists them and, with --apply, runs
the same sync an approval runs: the user gets the roles of the participant's
approved environments. Participants with no approved environment (sign-ups
still waiting, or rejected) are skipped: their user is created when an
administrator approves UAT. The sandbox never stores passwords in clear, so
these users have none until the participant's next portal sign-in sets it.

With --existing, the participants that already have a user are synced
instead (nobody is created), e.g. after the environment roles changed: the
retired ``sandbox`` role is replaced by ``uat``.

    python scripts/keycloak/backfill_users.py            # dry run: list only
    python scripts/keycloak/backfill_users.py --apply
    python scripts/keycloak/backfill_users.py --existing --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.app import ParticipantIamUser  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.services import iam_user_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Create the users (default: list only)")
    parser.add_argument(
        "--existing", action="store_true", help="Sync the participants that already have a user instead"
    )
    args = parser.parse_args()
    if not iam_user_service.is_enabled():
        print("Keycloak provisioning is off or not configured (KEYCLOAK_* settings).", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing = set(db.execute(select(ParticipantIamUser.participant_id)).scalars())
        missing = [
            p
            for p in db.execute(select(Participant).where(Participant.is_deleted.is_(False))).scalars()
            if (p.participant_id in existing) == args.existing
        ]
        for participant in missing:
            roles = ",".join(sorted(iam_user_service.roles_for(participant))) or "-"
            if args.apply:
                row = iam_user_service.sync(db, participant)
                print(f"{participant.email_id:40} roles {roles:20} {row.status if row else 'skipped'}")
            else:
                if args.existing:
                    action = "would be synced"
                elif roles == "-":
                    action = "skipped (no approved environment)"
                else:
                    action = "would be created"
                print(f"{participant.email_id:40} roles {roles:20} {action}")
        print(f"{len(missing)} user(s) {'processed' if args.apply else 'to process (dry run; add --apply)'}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
