"""Reference data used to bootstrap a new OAN deployment.

Kept separate from the seeding logic so the values can be reviewed and edited
without reading through the insert code.
"""

from __future__ import annotations

ETHIOPIA = {
    "country_code": "ET",
    "country_code3": "ETH",
    "country_name": "Ethiopia",
    "currency_code": "ETB",
    "dial_code": "251",
    "default_locale": "en",
    "supported_locales": ["en", "am", "om", "ti"],
    "level_labels": {"1": "Region", "2": "Zone", "3": "Woreda", "4": "Kebele"},
    "level_depth": 4,
    "is_live": True,
}

#: Countries pre-registered as prospective network members. Only Ethiopia is
#: live; the rest are placeholders an operator activates when onboarding.
OTHER_COUNTRIES = [
    {
        "country_code": "KE",
        "country_code3": "KEN",
        "country_name": "Kenya",
        "currency_code": "KES",
        "dial_code": "254",
        "supported_locales": ["en", "sw"],
        "level_labels": {"1": "County", "2": "Sub-county", "3": "Ward", "4": "Village"},
        "level_depth": 4,
    },
    {
        "country_code": "RW",
        "country_code3": "RWA",
        "country_name": "Rwanda",
        "currency_code": "RWF",
        "dial_code": "250",
        "supported_locales": ["en", "rw", "fr"],
        "level_labels": {"1": "Province", "2": "District", "3": "Sector", "4": "Cell"},
        "level_depth": 4,
    },
    {
        "country_code": "GH",
        "country_code3": "GHA",
        "country_name": "Ghana",
        "currency_code": "GHS",
        "dial_code": "233",
        "supported_locales": ["en"],
        "level_labels": {"1": "Region", "2": "District", "3": "Area", "4": "Community"},
        "level_depth": 4,
    },
    {
        "country_code": "NG",
        "country_code3": "NGA",
        "country_name": "Nigeria",
        "currency_code": "NGN",
        "dial_code": "234",
        "supported_locales": ["en"],
        "level_labels": {"1": "State", "2": "LGA", "3": "Ward", "4": "Community"},
        "level_depth": 4,
    },
]

#: Ethiopian regions and chartered city administrations, with their Amharic
#: names. Codes follow the national CSA numbering.
ETHIOPIA_REGIONS = [
    ("01", "Tigray", "ትግራይ"),
    ("02", "Afar", "አፋር"),
    ("03", "Amhara", "አማራ"),
    ("04", "Oromia", "ኦሮሚያ"),
    ("05", "Somali", "ሶማሌ"),
    ("06", "Benishangul-Gumuz", "ቤንሻንጉል ጉሙዝ"),
    ("07", "South Ethiopia", "ደቡብ ኢትዮጵያ"),
    ("08", "Gambela", "ጋምቤላ"),
    ("09", "Harari", "ሐረሪ"),
    ("10", "Sidama", "ሲዳማ"),
    ("11", "South West Ethiopia Peoples", "ደቡብ ምዕራብ ኢትዮጵያ"),
    ("12", "Central Ethiopia", "ማዕከላዊ ኢትዮጵያ"),
    ("14", "Addis Ababa", "አዲስ አበባ"),
    ("15", "Dire Dawa", "ድሬ ዳዋ"),
]

#: A representative zone set for the largest regions. A full national import is
#: loaded separately from the CSA dataset.
ETHIOPIA_ZONES = {
    "04": [
        ("0401", "West Shewa", "ምዕራብ ሸዋ"),
        ("0402", "East Shewa", "ምስራቅ ሸዋ"),
        ("0403", "Arsi", "አርሲ"),
        ("0404", "Bale", "ባሌ"),
        ("0405", "Jimma", "ጅማ"),
        ("0406", "West Wellega", "ምዕራብ ወለጋ"),
        ("0407", "East Wellega", "ምስራቅ ወለጋ"),
        ("0408", "Borena", "ቦረና"),
    ],
    "03": [
        ("0301", "North Gondar", "ሰሜን ጎንደር"),
        ("0302", "South Gondar", "ደቡብ ጎንደር"),
        ("0303", "North Wollo", "ሰሜን ወሎ"),
        ("0304", "South Wollo", "ደቡብ ወሎ"),
        ("0305", "East Gojjam", "ምስራቅ ጎጃም"),
        ("0306", "West Gojjam", "ምዕራብ ጎጃም"),
        ("0307", "Awi", "አዊ"),
    ],
    "01": [
        ("0101", "Central Tigray", "ማእከላይ ትግራይ"),
        ("0102", "Eastern Tigray", "ምብራቕ ትግራይ"),
        ("0103", "Southern Tigray", "ደቡብ ትግራይ"),
        ("0104", "Western Tigray", "ምዕራብ ትግራይ"),
    ],
    "10": [
        ("1001", "Hawassa", "ሀዋሳ"),
        ("1002", "Sidama Central", "ማእከላዊ ሲዳማ"),
    ],
    "14": [
        ("1401", "Addis Ababa City", "አዲስ አበባ ከተማ"),
    ],
}

#: ``kind -> [(name, code)]``. ``code`` is only used where the table has one.
LOOKUP_SEEDS: dict[str, list[tuple[str, str | None]]] = {
    "participant-type": [
        ("Agri Information Provider", "AIP"),
        ("Agri Information User", "AIU"),
        ("Solution Partner", "SP"),
    ],
    "service-domain": [
        ("Advisory Services", None),
        ("Credit and Lending", None),
        ("Crop Insurance", None),
        ("Input Distribution", None),
        ("Market Linkage", None),
        ("Traceability", None),
        ("Weather and Climate", None),
        ("Land Administration", None),
    ],
    "operating-area": [
        ("National", None),
        ("Regional", None),
        ("Zonal", None),
        ("Woreda", None),
        ("Cross-border", None),
    ],
    "category": [
        ("Farmer Services", None),
        ("Financial Services", None),
        ("Supply Chain", None),
        ("Advisory and Extension", None),
        ("Land and Assets", None),
    ],
}

#: ``category name -> sub-categories``
SUB_CATEGORY_SEEDS: dict[str, list[str]] = {
    "Farmer Services": ["Registry Lookup", "Profile Verification", "Household Data"],
    "Financial Services": [
        "Credit Scoring",
        "Loan Origination",
        "Insurance Underwriting",
    ],
    "Supply Chain": ["Input Traceability", "Produce Aggregation", "Warehouse Receipts"],
    "Advisory and Extension": [
        "Agronomic Advisory",
        "Pest and Disease Alerts",
        "Weather Advisory",
    ],
    "Land and Assets": ["Parcel Records", "Land Certification", "Asset Registry"],
}

PRODUCT_CATEGORY_SEEDS = [
    ("Farmer Registry", "Identity and profile APIs for registered farmers."),
    ("Land Registry", "Parcel, ownership and land-use APIs."),
    ("Crop and Season", "Sown area, crop type and seasonal production APIs."),
    ("Advisory", "Agronomic, weather and market advisory APIs."),
    ("Financial Services", "Credit, insurance and subsidy APIs."),
]

#: ``(code, name, subject, body)``. Bodies use ``{{placeholder}}`` markers.
EMAIL_TEMPLATE_SEEDS = [
    (
        "PARTICIPANT_OTP",
        "Email verification code",
        "Your OAN verification code",
        "<p>Hello,</p><p>Your verification code is <strong>{{otp}}</strong>. "
        "It expires in {{validity_minutes}} minutes.</p>"
        "<p>If you did not request this code, please ignore this email.</p>",
    ),
    (
        "PARTICIPANT_WELCOME",
        "Account activated",
        "Welcome to Open Agri Net",
        "<p>Dear {{name}},</p><p>Your email address is verified and your Open Agri "
        "Net account is active. Sandbox access is enabled straight away - sign in "
        "at {{portal_url}} to browse the API catalogue and start making calls.</p>"
        "<p>When you are ready to move beyond the sandbox, complete your "
        "organisation profile and request UAT access from your dashboard.</p>",
    ),
    (
        "PARTICIPANT_APPROVED",
        "Access approved",
        "Your OAN {{environment}} access is approved",
        "<p>Dear {{name}},</p><p>Your access to the OAN {{environment}} environment "
        "has been approved. You can sign in at {{portal_url}} to explore the API "
        "catalogue.</p>",
    ),
    (
        "PARTICIPANT_REJECTED",
        "Access not approved",
        "Update on your OAN application",
        "<p>Dear {{name}},</p><p>Your application was not approved for the following "
        "reason:</p><p>{{reason}}</p><p>You may correct the details and reapply.</p>",
    ),
    (
        "PARTICIPANT_RESET_PASSWORD",
        "Password reset",
        "Reset your OAN password",
        "<p>Dear {{name}},</p><p>Use the link below to set a new password. The link "
        "expires in two hours.</p><p>{{portal_url}}/participant/reset-password?token={{token}}</p>",
    ),
    (
        "PROMOTION_APPROVED",
        "Environment access approved",
        "{{environment}} access approved",
        "<p>Dear {{name}},</p><p>Your request for {{environment}} access has been "
        "approved.</p>",
    ),
    (
        "PROMOTION_REJECTED",
        "Environment access declined",
        "{{environment}} access request declined",
        "<p>Dear {{name}},</p><p>Your request for {{environment}} access was declined:"
        "</p><p>{{reason}}</p>",
    ),
    (
        "ADMIN_INVITE",
        "Administrator invitation",
        "You have been invited to the OAN console",
        "<p>Dear {{name}},</p><p>An account has been created for you on the Open Agri "
        "Net console. Set your password using the link below.</p>"
        "<p>{{portal_url}}/admin/set-password?token={{token}}</p>",
    ),
    (
        "ADMIN_RESET_PASSWORD",
        "Administrator password reset",
        "Reset your OAN console password",
        "<p>Dear {{name}},</p><p>Use the link below to set a new password. The link "
        "expires in 24 hours.</p>"
        "<p>{{portal_url}}/admin/set-password?token={{token}}</p>",
    ),
    (
        "QUERY_RESPONSE",
        "Support query response",
        "Response to your query: {{subject}}",
        "<p>Dear {{name}},</p><p>Our team has responded to your query:</p>"
        "<blockquote>{{response}}</blockquote>",
    ),
]

FAQ_SEEDS = [
    (
        "Getting Started",
        [
            (
                "What is Open Agri Net?",
                "Open Agri Net (OAN) is a shared digital infrastructure that lets "
                "accredited organisations exchange agricultural data through "
                "consented, standardised APIs. It is open to every country that "
                "joins the network.",
            ),
            (
                "Who can register?",
                "Registered organisations - agri-technology providers, financial "
                "institutions, cooperatives, government agencies and research "
                "institutions - as well as individual developers building on the "
                "network.",
            ),
            (
                "How long does approval take?",
                "Sandbox access is usually reviewed within three working days. UAT "
                "and production promotions take longer because they include a "
                "technical and compliance assessment.",
            ),
        ],
    ),
    (
        "Using the Sandbox",
        [
            (
                "What data does the sandbox return?",
                "The sandbox serves synthetic data that matches the production "
                "schema exactly. No real farmer records are exposed at this stage.",
            ),
            (
                "Are there rate limits?",
                "Sandbox traffic is limited to 60 requests per minute per "
                "user. UAT and production limits are agreed during "
                "onboarding.",
            ),
            (
                "How do I move from sandbox to production?",
                "Complete UAT certification first, then raise a production request "
                "from your dashboard with the required compliance documents.",
            ),
        ],
    ),
    (
        "Security and Compliance",
        [
            (
                "How is data protected in transit?",
                "All traffic uses TLS 1.2 or higher. Production payloads are "
                "additionally signed, and credentials are never logged.",
            ),
            (
                "What are my obligations as a network user?",
                "You must use the data only for the purpose declared during "
                "registration, retain it no longer than agreed, and report any "
                "suspected breach within 24 hours.",
            ),
        ],
    ),
]

TERMS_SEEDS = [
    (
        "Introduction",
        "<p>These terms govern access to the Open Agri Net (OAN) developer sandbox "
        "and the APIs published through it. By registering for an account you "
        "accept these terms in full.</p>",
    ),
    (
        "Eligibility",
        "<p>Participation is open to legally registered entities and to individual "
        "developers who complete identity verification. The network operator may "
        "decline or revoke access where eligibility cannot be established.</p>",
    ),
    (
        "Acceptable Use",
        "<p>Users must use OAN APIs only for the purposes declared at "
        "registration. Bulk extraction, resale of data, or use outside the "
        "declared service domain is prohibited.</p>",
    ),
    (
        "Data Protection",
        "<p>Users act as data processors for records obtained through the "
        "network and must apply appropriate technical and organisational "
        "safeguards. Personal data may not be retained beyond the agreed "
        "retention period.</p>",
    ),
    (
        "Service Levels",
        "<p>The sandbox is provided on a best-effort basis and carries no "
        "availability guarantee. Production service levels are set out in the "
        "participation agreement signed at onboarding.</p>",
    ),
]

HOME_BLOCK_SEEDS = [
    {
        "block_key": "hero",
        "title": "Build on an open agricultural data network",
        "subtitle": "Open Agri Net gives accredited organisations consented, "
        "standardised access to farmer, land and crop data.",
        "content": {
            "primary_cta": {"label": "Create an account", "href": "/register"},
            "secondary_cta": {"label": "Explore the API catalogue", "href": "/catalog"},
        },
        "sort_order": 1,
    },
    {
        "block_key": "value_props",
        "title": "Why build on OAN",
        "content": {
            "items": [
                {
                    "title": "One integration, many services",
                    "body": "Connect once and reach registry, land, crop and advisory "
                    "data through a single consistent contract.",
                },
                {
                    "title": "Consent at the core",
                    "body": "Every record is released against a recorded lawful basis, "
                    "with a full audit trail.",
                },
                {
                    "title": "Built to cross borders",
                    "body": "The same contracts and tooling extend to every member "
                    "country that joins the network.",
                },
            ]
        },
        "sort_order": 2,
    },
    {
        "block_key": "how_it_works",
        "title": "From registration to production",
        "content": {
            "steps": [
                {
                    "step": 1,
                    "title": "Register",
                    "body": "Submit your organisation details and supporting documents.",
                },
                {
                    "step": 2,
                    "title": "Explore the sandbox",
                    "body": "Test against synthetic data with full API references.",
                },
                {
                    "step": 3,
                    "title": "Certify in UAT",
                    "body": "Validate your integration against pre-production services.",
                },
                {
                    "step": 4,
                    "title": "Go live",
                    "body": "Request production access and start serving real users.",
                },
            ]
        },
        "sort_order": 3,
    },
]
