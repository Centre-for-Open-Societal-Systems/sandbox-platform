"""HTTP layer.

``api_router`` mounts every module under the configured API prefix:

* ``/oan``              - public content and the API catalogue
* ``/oan/admin``        - back-office console
* ``/oan/participant``  - participant portal and sandbox console

Inside the console, ``/oan/admin/participants`` manages network participants
and ``/oan/admin/users`` manages back-office accounts - two different
audiences, two different words.
"""

from fastapi import APIRouter

from app.config.settings import settings
from app.controllers import home_controller
from app.controllers.admin import (
    auth_controller as admin_auth_controller,
)
from app.controllers.admin import (
    catalog_controller as admin_catalog_controller,
)
from app.controllers.admin import (
    content_controller as admin_content_controller,
)
from app.controllers.admin import (
    log_controller as admin_log_controller,
)
from app.controllers.admin import (
    master_controller as admin_master_controller,
)
from app.controllers.admin import (
    participant_controller as admin_participant_controller,
)
from app.controllers.admin import (
    user_controller as admin_user_controller,
)
from app.controllers.participant import (
    auth_controller as participant_auth_controller,
)
from app.controllers.participant import (
    portal_controller as participant_portal_controller,
)
from app.controllers.participant import (
    sandbox_controller as participant_sandbox_controller,
)

api_router = APIRouter(prefix=settings.API_PREFIX)

api_router.include_router(home_controller.router)

admin_router = APIRouter(prefix="/admin")
admin_router.include_router(admin_auth_controller.router)
admin_router.include_router(admin_user_controller.router)
admin_router.include_router(admin_participant_controller.router)
admin_router.include_router(admin_catalog_controller.router)
admin_router.include_router(admin_master_controller.router)
admin_router.include_router(admin_content_controller.router)
admin_router.include_router(admin_log_controller.router)

participant_router = APIRouter(prefix="/participant")
participant_router.include_router(participant_auth_controller.router)
participant_router.include_router(participant_portal_controller.router)
participant_router.include_router(participant_sandbox_controller.router)

api_router.include_router(admin_router)
api_router.include_router(participant_router)

__all__ = ["api_router"]
