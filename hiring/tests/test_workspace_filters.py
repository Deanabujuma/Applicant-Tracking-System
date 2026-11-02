"""Phase 10 Test 1: search (``q``) and the stage filter (``stage``) in the workspace."""

import re
from html import unescape

import pytest
from django.utils.http import urlencode

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from hiring.tests.test_stage_moves import sidebar_count
from hiring.tests.test_workspace_selection import (
    HTMX,
    applicant_items,
    attr,
    current_hrefs,
    stage_summary,
    total,
)
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
NO_MATCH = "No matching applications."


@pytest.fixture
def employee_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="jsmith"))
    return client


@pytest.fixture
def data(django_user_model):
    """Ana applied to both openings; "ana" also appears inside "Dana"."""
    employee = django_user_model.objects.create_user(username="recruiter")
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    designer = JobOpening.objects.create(title="Designer", department="Art")

    def person(first, last, email, archived=False):
        return Candidate.objects.create(
            first_name=first,
            last_name=last,
            email=email,
            source=Source.REFERRAL,
            is_archived=archived,
        )

    ana = person("Ana", "Zimmer", "ana.z@example.com")
    ben = person("Ben", "Young", "ben@corp.test")
    cara = person("Cara", "Xu", "cara@example.com", archived=True)
    dana = person("Dana", "Lopez", "dlopez@mail.test")

    def apply(candidate, opening, stage):
        return Application.objects.create(
            candidate=candidate, opening=opening, stage=stage, stage_changed_by=employee
        )

    return {
        "analyst": analyst,
        "designer": designer,
        "ana_analyst": apply(ana, analyst, S.SCREENING),
        "ana_designer": apply(ana, designer, S.APPLIED),
        "ben_analyst": apply(ben, analyst, S.APPLIED),
        "cara_analyst": apply(cara, analyst, S.REJECTED),
        "dana_designer": apply(dana, designer, S.SCREENING),
    }


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def get(client, query, **headers):
    response = client.get(f"/?{query}", **headers)
    assert response.status_code == 200, query
    return response.content.decode()


def listed(page):
    return {pk for pk, _ in applicant_items(page)}


def pks(data, *names):
    return {data[name].pk for name in names}


def counts(page):
    return {stage: count for stage, (_, count) in stage_summary(page).items()}


def stage_link(page, stage):
    """The attributes of the link inside one stage's summary item."""
    item = stage_summary(page)[stage.value][0]
    match = re.search(r"<a\b([^>]*)>", item)
    assert match, f"{stage.label} count isn't a link"
    return match.group(1)


def all_stages_link(page):
    match = re.search(r'<a\b([^>]*\bid="all-stages"[^>]*)>\s*All stages\s*</a>', page)
    assert match, "no All stages link"
    return match.group(1)


# --- Search -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("ana", ["ana_analyst", "ana_designer", "dana_designer"]),  # substring
        ("ANA", ["ana_analyst", "ana_designer", "dana_designer"]),  # any case
        ("zimmer", ["ana_analyst", "ana_designer"]),  # last name
        ("  ZIMMER  ", ["ana_analyst", "ana_designer"]),  # trimmed
        ("ana zimmer", ["ana_analyst", "ana_designer"]),  # full name
        ("Dana Lopez", ["dana_designer"]),
        ("corp.test", ["ben_analyst"]),  # email
        ("ANA.Z@EXAMPLE.COM", ["ana_analyst", "ana_designer"]),
        ("xu", ["cara_analyst"]),  # archived candidates are searchable
    ],
)
def test_search_across_all_openings(employee_client, data, q, expected):
    before = snapshot()

    page = get(employee_client, f"opening=all&q={q}")

    assert listed(page) == pks(data, *expected)
    items = dict(applicant_items(page))
    for name in expected:
        application = data[name]
        item = items[application.pk]
        assert application.opening.title in item  # job title still shown
        assert (">Archived</span>" in item) is application.candidate.is_archived
        assert f"application={application.pk}" in unescape(item)  # still a link
    # Phase 10 Test 3: the sidebar keeps the (trimmed) search.
    assert current_hrefs(page) == [f"/?opening=all&amp;{urlencode({'q': q.strip()})}"]
    assert snapshot() == before


def test_search_within_a_selected_opening(employee_client, data):
    analyst, designer = data["analyst"], data["designer"]

    assert listed(get(employee_client, f"opening={analyst.pk}&q=ana")) == pks(
        data, "ana_analyst"
    )
    assert listed(get(employee_client, f"opening={designer.pk}&q=ana")) == pks(
        data, "ana_designer", "dana_designer"
    )
    page = get(employee_client, f"opening={analyst.pk}&q=dana")
    assert listed(page) == set()
    assert NO_MATCH in page
    assert current_hrefs(page) == [f"/?opening={analyst.pk}&amp;q=dana"]


def test_empty_or_blank_search_shows_everything(employee_client, data):
    everyone = {app.pk for app in Application.objects.all()}
    for query in ("opening=all&q=", "opening=all&q=%20%20%20", "opening=all"):
        page = get(employee_client, query)
        assert listed(page) == everyone, query
        assert NO_MATCH not in page


# --- Stage filter -----------------------------------------------------------


def test_stage_filter_shows_only_that_stage(employee_client, data):
    before = snapshot()

    page = get(employee_client, "opening=all&stage=screening")
    assert listed(page) == pks(data, "ana_analyst", "dana_designer")

    page = get(employee_client, f"opening={data['analyst'].pk}&stage=applied")
    assert listed(page) == pks(data, "ben_analyst")

    page = get(employee_client, f"opening={data['designer'].pk}&stage=hired")
    assert listed(page) == set()
    assert NO_MATCH in page
    assert snapshot() == before


def test_stage_counts_are_filter_links_with_all_stages(employee_client, data):
    scope = str(data["analyst"].pk)

    page = get(employee_client, f"opening={scope}")
    for stage in Stage:
        link = stage_link(page, stage)
        url = f"/?opening={scope}&stage={stage.value}"
        assert unescape(attr(link, "href")) == url
        assert unescape(attr(link, "hx-get")) == url
        assert attr(link, "hx-target") == "#workspace"
        assert attr(link, "hx-swap") == "outerHTML"
        assert attr(link, "hx-push-url") == "true"
        assert attr(link, "aria-current") is None  # no stage filter yet
    every = all_stages_link(page)
    assert unescape(attr(every, "href")) == f"/?opening={scope}"
    assert unescape(attr(every, "hx-get")) == f"/?opening={scope}"
    assert attr(every, "aria-current") == "true"

    # Following a stage link filters to it and marks only it as current.
    url = unescape(attr(stage_link(page, S.APPLIED), "href"))
    filtered = employee_client.get(url).content.decode()
    assert listed(filtered) == pks(data, "ben_analyst")
    marked = [
        s for s in Stage if attr(stage_link(filtered, s), "aria-current") == "true"
    ]
    assert marked == [S.APPLIED]
    assert attr(all_stages_link(filtered), "aria-current") is None

    # All stages clears it.
    cleared = employee_client.get(
        unescape(attr(all_stages_link(filtered), "href"))
    ).content.decode()
    assert listed(cleared) == pks(data, "ana_analyst", "ben_analyst", "cara_analyst")


# --- Together, and the counts -----------------------------------------------


def test_search_and_stage_filter_combine(employee_client, data):
    page = get(employee_client, "opening=all&q=ana&stage=screening")
    assert listed(page) == pks(data, "ana_analyst", "dana_designer")

    page = get(employee_client, "opening=all&q=zimmer&stage=applied")
    assert listed(page) == pks(data, "ana_designer")

    page = get(employee_client, "opening=all&q=ben&stage=screening")
    assert listed(page) == set()
    assert NO_MATCH in page


def test_counts_follow_scope_and_search_but_not_the_stage_filter(employee_client, data):
    analyst, designer = data["analyst"], data["designer"]
    expected_ana = {s.value: 0 for s in Stage} | {"screening": 2, "applied": 1}

    for stage_part in ("", "&stage=screening", "&stage=hired"):
        page = get(employee_client, f"opening=all&q=ana{stage_part}")
        assert counts(page) == expected_ana, stage_part
        assert total(page) == 3
        # The sidebar's active counts ignore every filter.
        assert sidebar_count(page, analyst) == 2
        assert sidebar_count(page, designer) == 2

    page = get(employee_client, f"opening={analyst.pk}&q=zimmer&stage=applied")
    assert counts(page)["screening"] == 1
    assert total(page) == 1
    assert listed(page) == set()  # Ana's analyst application is in Screening


# --- Bad values, HTMX, read-only --------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "stage=bogus",
        "stage=Applied",  # stage values, not labels
        "stage=final%20review",
        "q=" + "x" * 101,
        "q=" + "x" * 50 + "%20" * 2 + "y" * 50,  # 102 characters inside
    ],
    ids=["unknown", "label", "spaced", "too-long", "too-long-inner"],
)
def test_bad_filter_values_are_400(employee_client, data, query):
    before = snapshot()
    for headers in ({}, HTMX):
        assert (
            employee_client.get(f"/?opening=all&{query}", **headers).status_code == 400
        )
    assert snapshot() == before


def test_search_of_exactly_100_characters_is_allowed(employee_client, data):
    page = get(employee_client, "opening=all&q=" + "x" * 100)
    assert listed(page) == set()
    assert NO_MATCH in page


def test_filtered_requests_keep_partial_and_full_page_behaviour(employee_client, data):
    query = f"opening={data['designer'].pk}&q=ana&stage=screening"
    before = snapshot()

    full = get(employee_client, query)
    partial = get(employee_client, query, **HTMX).strip()

    assert "<html" in full
    assert full.count('id="workspace"') == 1
    assert partial.startswith('<div id="workspace"')
    assert "<html" not in partial
    assert listed(full) == listed(partial) == pks(data, "dana_designer")
    assert snapshot() == before


def test_no_filters_and_no_applications_still_says_none_yet(employee_client):
    page = get(employee_client, "opening=all")
    assert "No applications yet." in page
    assert NO_MATCH not in page
