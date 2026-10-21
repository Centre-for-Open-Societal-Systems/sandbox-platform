"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata`` - which is
what Alembic autogenerate and ``create_all`` rely on, so keep the re-exports
below in sync when a model file is added.
"""

from app.models.admin import (
    AdmPermission,
    AdmRole,
    AdmRolePermission,
    AdmToken,
    AdmUser,
)
from app.models.catalog import Endpoint, EndpointSchema, MapperData, Product
from app.models.content import (
    EmailTemplate,
    FaqDetail,
    FaqType,
    HomePageBlock,
    TermCondition,
)
from app.models.geo import AdminArea, Country
from app.models.logs import ApiLog, SandboxLog, UserActionLog
from app.models.masters import (
    Category,
    OperatingArea,
    ParticipantType,
    ProductCategory,
    ServiceDomain,
    SubCategory,
)
from app.models.participant import (
    Participant,
    ParticipantQuery,
    ParticipantRequestInfo,
    ParticipantToken,
)

__all__ = [
    # admin
    "AdmUser",
    "AdmRole",
    "AdmPermission",
    "AdmRolePermission",
    "AdmToken",
    # geo
    "Country",
    "AdminArea",
    # masters
    "ParticipantType",
    "ServiceDomain",
    "OperatingArea",
    "Category",
    "SubCategory",
    "ProductCategory",
    # participants
    "Participant",
    "ParticipantToken",
    "ParticipantRequestInfo",
    "ParticipantQuery",
    # catalog
    "Product",
    "Endpoint",
    "EndpointSchema",
    "MapperData",
    # content
    "FaqType",
    "FaqDetail",
    "TermCondition",
    "EmailTemplate",
    "HomePageBlock",
    # logs
    "ApiLog",
    "UserActionLog",
    "SandboxLog",
]
