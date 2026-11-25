"""The OpenG2P contract the sandbox is built against: one place to change when
OpenG2P changes Partner Management (PM) or the Consent Manager (CM).

* ``PM_PROFILES`` - what each PM version offers (capabilities) and the upstream
  commit it was checked against. ``PM_API_VERSION`` / ``PM_PROD_API_VERSION`` pick one
  (``auto``: ``GET /metadata`` answers on develop only, so 404 = 1.0).
* ``PM_POLICY_FIELDS`` etc. - PM PolicyInput as the sandbox sends it; the API
  product form validates against these.
* ``CM_*`` - the COSS Consent Manager binding/policy API used while COSS keeps data
  policies there (``POLICY_BACKEND=cm``).
* ``WATCHED`` - the upstream files whose change may change this contract; the
  watcher (``scripts/openg2p/check_upstream.py``, weekly in CI) reports new upstream
  commits touching them, new release branches / tags, and field / route drift
  against the values below.

Upgrading (docs/OPENG2P_INTEGRATION.md): run the watcher, read its report, change
the profile / fields here and the code using them, run the tests, then move the
pinned ``ref`` to the commit you checked.
"""

from __future__ import annotations

from dataclasses import dataclass

PM_REPO = "https://github.com/OpenG2P/partner-management"
CM_REPO = "https://github.com/Centre-for-Open-Societal-Systems/consent-management"


@dataclass(frozen=True, slots=True)
class PmProfile:
    """What one PM version offers the sandbox."""

    name: str
    #: Upstream branch and the commit this profile was checked against.
    branch: str
    ref: str
    #: Helm chart version(s) known to ship it (openg2p-helm ``partner-management``).
    charts: tuple[str, ...]
    #: ``keys_from_jwks_url``: PM reads the partner's keys from the sandbox's JWKS when
    #: needed. Without it a key is required to onboard (copied once with
    #: ``import_from_jwks_url``) and a changed key needs a key-update request.
    live_jwks: bool
    #: Onboarding / policy requests carry access policies (``/partners/requests/policy``).
    policies: bool
    #: ``use_case`` policies (``name@major``) next to registry scope policies.
    use_cases: bool
    #: ``GET /catalogue`` (registries' scopes, use cases) and ``GET /metadata``.
    catalogue: bool
    #: ``allow_partner_consents`` on a policy.
    partner_consents: bool


PM_PROFILES: dict[str, PmProfile] = {
    # Released line, deployed by COSS (openg2p-commons-services -> partner-management 1.0.2).
    "1.0": PmProfile("1.0", "1.0", "b5232da", ("1.0.2", "1.0.3"), live_jwks=False, policies=False,
                     use_cases=False, catalogue=False, partner_consents=False),
    # Development line with access policies (G2P-5719), not yet in COSS.
    "develop": PmProfile("develop", "develop", "33dd782", ("0.0.0-develop",), live_jwks=True, policies=True,
                         use_cases=True, catalogue=True, partner_consents=True),
}

#: PolicyInput fields of PM ``develop`` the sandbox sends (schemas/policy.py).
PM_POLICY_FIELDS = (
    "data_controller", "use_case", "allowed_data_scopes", "allowed_purposes", "allowed_subject_id_types",
    "allowed_signing_algs", "max_validity_duration", "fetch_type", "max_fetch_frequency", "data_life",
    "allow_partner_consents",
)
#: OnboardingRequestCreate fields per profile (schemas/request.py).
PM_ONBOARDING_FIELDS = {
    "1.0": ("partner_id", "name", "org_name", "description", "jwks_url", "keys", "import_from_jwks_url"),
    "develop": ("partner_id", "name", "org_name", "description", "jwks_url", "keys", "import_from_jwks_url",
                "keys_from_jwks_url", "policies"),
}
#: PM staff API routes the sandbox calls, per profile.
PM_ROUTES = {
    "1.0": ("/partners", "/partners/{partner_id}", "/partners/{partner_id}/keys", "/partners/{partner_id}/disable",
            "/partners/{partner_id}/enable", "/partners/requests/onboarding", "/partners/requests/key-update",
            "/partners/requests", "/partners/requests/{request_id}", "/partners/requests/{request_id}/approve"),
    "develop": ("/partners", "/partners/{partner_id}", "/partners/{partner_id}/keys",
                "/partners/{partner_id}/disable", "/partners/{partner_id}/enable", "/partners/requests/onboarding",
                "/partners/requests/key-update", "/partners/requests/policy", "/partners/requests",
                "/partners/requests/{request_id}", "/partners/requests/{request_id}/approve", "/catalogue",
                "/metadata"),
}
PM_IDENTIFIER_PATTERN = r"^[^\s/?#%]+$"
PM_USE_CASE_PATTERN = r"^[^\s/?#%@]+@\d+$"
PM_SIGNING_ALGS = ("RS256", "ES256", "EdDSA")
PM_FETCH_TYPES = ("oneshot", "periodic")

# ---------------------------------------------------------- COSS Consent Manager
#: The COSS CM checked against (consent-management develop).
CM_BRANCH, CM_REF = "develop", "32bce76"
#: PolicyUpsert fields (schemas/partner.py) - PM's registry policy fields, plus
#: consent_method instead of allow_partner_consents; no use cases.
CM_POLICY_FIELDS = (
    "allowed_data_scopes", "allowed_purposes", "allowed_subject_id_types", "allowed_signing_algs",
    "max_validity_duration", "fetch_type", "max_fetch_frequency", "data_life", "consent_method",
)
CM_ROUTES = ("/consent/v1/partners", "/consent/v1/partners/{partner_id}", "/consent/v1/partners/{partner_id}/policy",
             "/consent/v1/partners/{partner_id}/policies")
#: The CM role its staff API requires (config auth_admin_role).
CM_ADMIN_ROLE = "CONSENT_MANAGER_ADMIN"

# ------------------------------------------------------------- watched upstream
#: (repo, branch, pinned ref, files whose change may change the contract).
WATCHED = (
    (PM_REPO, "develop", PM_PROFILES["develop"].ref, (
        "core/api/src/openg2p_partner_management_api/schemas/",
        "core/api/src/openg2p_partner_management_api/controllers/",
        "core/api/src/openg2p_partner_management_api/models/",
        "core/api/src/openg2p_partner_management_api/config.py",
    )),
    (PM_REPO, "1.0", PM_PROFILES["1.0"].ref, (
        "core/api/src/openg2p_partner_management_api/schemas/",
        "core/api/src/openg2p_partner_management_api/controllers/",
        "core/api/src/openg2p_partner_management_api/models/",
    )),
    (CM_REPO, CM_BRANCH, CM_REF, (
        "backend/src/openg2p_consent_manager/schemas/partner.py",
        "backend/src/openg2p_consent_manager/controllers/partner_controller.py",
        "backend/src/openg2p_consent_manager/models/partner.py",
        "backend/src/openg2p_consent_manager/config.py",
    )),
)


def pm_profile(name: str) -> PmProfile:
    return PM_PROFILES.get(name) or PM_PROFILES["develop"]
