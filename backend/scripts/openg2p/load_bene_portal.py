"""Load two OpenG2P Beneficiary Portal endpoints into the OAN catalogue.

Run from sandbox-backend:  venv\\Scripts\\python.exe <this file>
Uses the same service layer as the admin console's "Import spec" action.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.deps import AdminPrincipal  # noqa: E402
from app.models.admin import AdmUser  # noqa: E402
from app.models.catalog import Endpoint, Product  # noqa: E402
from app.schemas.catalog import ProductCreate  # noqa: E402
from app.services import catalog_service  # noqa: E402

SPEC = Path(__file__).with_name("bene-portal.json")
KEEP = ["/beneficiary_portal/get_all_registers", "/beneficiary_portal/get_register"]
PRODUCT = "OpenG2P Beneficiary Portal"

spec = json.loads(SPEC.read_text(encoding="utf-8"))
spec["paths"] = {path: spec["paths"][path] for path in KEEP}

db = SessionLocal()
admin_user = db.execute(
    select(AdmUser).where(AdmUser.is_master.is_(True)).order_by(AdmUser.admin_id)
).scalars().first()
if admin_user is None:
    sys.exit("No master admin found - run `python -m app.seeds.seed` first.")
admin = AdminPrincipal(user=admin_user, auth_key="script", permissions=set())

product = db.execute(
    select(Product).where(Product.product_name == PRODUCT, Product.is_deleted.is_(False))
).scalars().first()
if product is None:
    created = catalog_service.create_product(
        db,
        admin,
        ProductCreate(
            product_name=PRODUCT,
            display_name="OpenG2P Registry - Beneficiary Portal API",
            description=(
                "Registry Beneficiary Portal API (OpenG2P Registry Gen2 v1.1.0): "
                "lets a logged-in beneficiary list registers and read their register data."
            ),
            api_doc_version=str(spec["info"]["version"]),
        ),
    )
    product_id = created.product_id
else:
    product_id = product.product_id

result = catalog_service.import_specification(
    db, admin, product_id, json.dumps(spec), replace_existing=False
)
print("import:", result)

# Publish product and endpoints so participants can see them in the portal.
catalog_service.publish_product(db, admin, product_id, True)
for endpoint in db.execute(
    select(Endpoint).where(Endpoint.product_id == product_id, Endpoint.is_deleted.is_(False))
).scalars():
    if not endpoint.is_published:
        catalog_service.publish_endpoint(db, admin, endpoint.endpoint_id, True)
    print(f"  endpoint {endpoint.endpoint_id}: {endpoint.method} {endpoint.endpoint_url}")

print("product_id:", product_id)
db.close()
