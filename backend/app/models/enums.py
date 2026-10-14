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
    """Promotion ladder a user climbs.

    ``SANDBOX`` is granted automatically once the email address is verified;
    ``UAT`` and ``PRODUCTION`` each need an admin decision.
    """

    SANDBOX = "SANDBOX"
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


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
