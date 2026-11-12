"""Domain enumerations.

Values are integers where the reference database stored integers, so data
migrated from an existing deployment keeps its meaning.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class ApprovalStatus(IntEnum):
    PENDING = 0
    APPROVED = 1
    REJECTED = 2


class ActivationStatus(IntEnum):
    NOT_ACTIVATED = 0
    ACTIVATED = 1
    BLOCKED = 2


class ProfileType(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    ORGANIZATION = "ORGANIZATION"


class Environment(StrEnum):
    """Promotion ladder a user climbs. Each step needs an admin decision.

    ``UAT`` is requested by signing up: the administrator reviews the sign-up
    details, and approval opens the portal (try-it, apps, keys).
    ``PRODUCTION`` is requested from the portal once the profile is complete.
    """

    UAT = "UAT"
    PRODUCTION = "PRODUCTION"


class ParticipantRole(StrEnum):
    """How a member participates in the network."""

    #: Agri Information Provider - publishes data into the network.
    AIP = "AIP"
    #: Agri Information User - consumes data from the network.
    AIU = "AIU"


class ApiType(StrEnum):
    """Which tier of the network serves an endpoint."""

    NATIONAL = "NATIONAL"
    REGIONAL = "REGIONAL"
    IAM = "IAM"
    PARTNER = "PARTNER"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class QueryStatus(IntEnum):
    OPEN = 0
    IN_PROGRESS = 1
    RESOLVED = 2
    CLOSED = 3


class ApprovalType(StrEnum):
    """How an app's request for an API product is decided."""

    #: Granted as soon as the app asks for it.
    AUTO = "AUTO"
    #: Waits for an administrator.
    MANUAL = "MANUAL"


class AppStatus(IntEnum):
    """A participant app. Keys exist only once an administrator approved it."""

    #: Created by the participant; waiting for an administrator. No keys yet.
    PENDING = 0
    #: Approved: holds keys and reaches the gateway.
    ACTIVE = 1
    #: Switched off by an administrator; its keys stop working at the gateway.
    REVOKED = 2
    #: The administrator declined the new app; the participant sees the reason.
    REJECTED = 3


class SubscriptionStatus(IntEnum):
    """An app's access to one API product."""

    PENDING = 0
    APPROVED = 1
    REJECTED = 2
    REVOKED = 3


class CredentialStatus(IntEnum):
    ACTIVE = 1
    REVOKED = 2
    #: Ran past ``expires_date`` (set by the maintenance sweep; never usable again).
    EXPIRED = 3


class GatewaySyncStatus(StrEnum):
    """Whether the gateway holds the app as the sandbox last saved it."""

    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    #: App provisioning is switched off (GATEWAY_APP_SYNC_ENABLED).
    DISABLED = "DISABLED"


class IamUserStatus(StrEnum):
    """A participant's Keycloak user, as the sandbox last left it."""

    #: Enabled, with at least one environment role.
    ACTIVE = "ACTIVE"
    #: Turned off in Keycloak: no approved environment yet, rejected, disabled or deleted.
    DISABLED = "DISABLED"
    #: Keycloak could not be updated; the admin console can retry.
    FAILED = "FAILED"


class ApiCallSource(StrEnum):
    """Where an API history row came from."""

    #: The portal's try-it console (recorded by the sandbox itself).
    TRYIT = "TRYIT"
    #: Called straight on the gateway with an app key (APISIX http-logger).
    DIRECT = "DIRECT"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
