"""Re-write every active app to Keycloak / the gateway.

Run after changing GATEWAY_SCOPES, GATEWAY_TOKEN_AUDIENCE, GATEWAY_LEGACY_ROUTE_CLAIM
or KEYCLOAK_PROD_CLIENT_AUTH (the console's Apps & Keys "Re-sync all" does the same,
POST /oan/admin/apps/gateway-sync-all). Tokens already issued keep their old claims
until they expire (five minutes).

    venv\\Scripts\\python.exe scripts\\keycloak\\resync_apps.py
    kubectl exec deploy/<sandbox api> -- python scripts/keycloak/resync_apps.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import SessionLocal  # noqa: E402
from app.services import app_service  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        result = app_service.resync_all(db)
    finally:
        db.close()
    print(f"{result['synced']} of {result['apps']} active app(s) synced, {result['failed']} failed.")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
