"""Public content endpoints and locale negotiation."""

from __future__ import annotations

from app.models.content import FaqDetail, FaqType, TermCondition


def _seed_faq(db_session) -> None:
    faq_type = FaqType(faq_type="Getting Started", sort_order=1)
    db_session.add(faq_type)
    db_session.flush()
    db_session.add(
        FaqDetail(
            type_id=faq_type.type_id,
            question="What is Open Agri Net?",
            answer="A shared agricultural data network.",
        )
    )
    db_session.commit()


def test_faqs_are_grouped_by_category(client, db_session):
    _seed_faq(db_session)

    response = client.get("/oan/faqs")

    assert response.status_code == 200
    groups = response.json()["data"]
    assert len(groups) == 1
    assert groups[0]["faq_type"] == "Getting Started"
    assert groups[0]["faqs"][0]["question"] == "What is Open Agri Net?"


def test_wildcard_accept_language_falls_back_to_english(client, db_session):
    """Some HTTP clients send `Accept-Language: *`, which is not a locale."""
    _seed_faq(db_session)

    response = client.get("/oan/faqs", headers={"accept-language": "*"})

    assert len(response.json()["data"]) == 1


def test_regional_accept_language_resolves_to_its_primary_subtag(client, db_session):
    _seed_faq(db_session)

    response = client.get("/oan/faqs", headers={"accept-language": "en-GB,en;q=0.9"})

    assert len(response.json()["data"]) == 1


def test_unknown_locale_returns_no_content_rather_than_english(client, db_session):
    _seed_faq(db_session)

    response = client.get("/oan/faqs", headers={"accept-language": "am"})

    assert response.json()["data"] == []


def test_terms_are_returned_in_sort_order(client, db_session):
    db_session.add_all(
        [
            TermCondition(
                sidebar_title="Eligibility", term_content="<p>b</p>", sort_order=2
            ),
            TermCondition(
                sidebar_title="Introduction", term_content="<p>a</p>", sort_order=1
            ),
        ]
    )
    db_session.commit()

    response = client.get("/oan/terms")

    titles = [section["sidebar_title"] for section in response.json()["data"]]
    assert titles == ["Introduction", "Eligibility"]


def test_health_reports_the_database(client):
    response = client.get("/oan/health")

    assert response.status_code == 200
    assert response.json()["data"]["database"] == "up"
