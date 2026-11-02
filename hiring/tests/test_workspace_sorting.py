"""Phase 10 Test 2: sorting the workspace applicant list (``sort``).

``sort`` is ``name`` (the default), ``stage``, ``updated`` or ``opening``;
a leading ``-`` reverses the option's own direction. Ties fall back to the
candidate's name and finally the application ID, always ascending.
"""

import datetime
import re
from html import unescape

import pytest
from django.utils import timezone
from django.utils.http import urlencode

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from hiring.tests.test_workspace_detail import detail_panel
from hiring.tests.test_workspace_selection import (
    HTMX,
    applicant_items,
    attr,
    stage_summary,
    total,
)
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
BASE = timezone.now() - datetime.timedelta(days=30)
OPTIONS = ["name", "stage", "updated", "opening"]
SORTS = OPTIONS + [f"-{option}" for option in OPTIONS]

# (first, last, opening, stage, days after BASE, archived). Rows 0 and 2 tie
# on name, stage and time, so only the application ID orders them.
ROWS = [
    ("Ana", "Doe", "analyst", S.INTERVIEW, 2, False),  # 0
    ("Ben", "Doe", "designer", S.APPLIED, 5, False),  # 1
    ("Ana", "Doe", "designer", S.INTERVIEW, 2, False),  # 2
    ("Cara", "Adams", "analyst", S.WITHDRAWN, 1, False),  # 3
    ("Dev", "Young", "analyst", S.FINAL_REVIEW, 4, False),  # 4
    ("Eve", "Brown", "designer", S.REJECTED, 3, True),  # 5
    ("Finn", "Clark", "analyst", S.SCREENING, 6, False),  # 6
    ("Gus", "Hill", "analyst", S.OFFER, 7, False),  # 7
    ("Hana", "Ito", "analyst", S.HIRED, 0, False),  # 8
]

# The agreed order of every row, by sort, in All Openings (row numbers above).
EXPECTED = {
    # last name, first name, ID
    "name": [3, 5, 6, 0, 2, 1, 7, 8, 4],
    "-name": [4, 8, 7, 1, 0, 2, 6, 5, 3],
    # pipeline order, not alphabetical
    "stage": [1, 6, 0, 2, 4, 7, 8, 5, 3],
    "-stage": [3, 5, 8, 7, 4, 0, 2, 6, 1],
    # latest stage change first
    "updated": [7, 6, 1, 4, 5, 0, 2, 3, 8],
    "-updated": [8, 3, 0, 2, 5, 4, 1, 6, 7],
    # job title ("Brand Designer" before "Data Analyst")
    "opening": [5, 2, 1, 3, 6, 0, 7, 8, 4],
    "-opening": [3, 6, 0, 7, 8, 4, 5, 2, 1],
}
REVERSED = {"name": "-name", "-name": "name", "stage": "-stage", "-stage": "stage"} | {
    "updated": "-updated",
    "-updated": "updated",
    "opening": "-opening",
    "-opening": "opening",
}


@pytest.fixture
def employee_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="jsmith"))
    return client


@pytest.fixture
def data(django_user_model):
    employee = django_user_model.objects.create_user(username="recruiter")
    openings = {
        "analyst": JobOpening.objects.create(
            title="Data Analyst", department="Finance"
        ),
        "designer": JobOpening.objects.create(title="Brand Designer", department="Art"),
    }
    rows = []
    for n, (first, last, opening, stage, days, archived) in enumerate(ROWS):
        candidate = Candidate.objects.create(
            first_name=first,
            last_name=last,
            email=f"{first.lower()}{n}@example.com",
            source=Source.REFERRAL,
            is_archived=archived,
        )
        application = Application.objects.create(
            candidate=candidate,
            opening=openings[opening],
            stage=stage,
            stage_changed_by=employee,
        )
        Application.objects.filter(pk=application.pk).update(
            stage_changed_at=BASE + datetime.timedelta(days=days)
        )
        rows.append(application)
    return openings | {"rows": rows}


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


def order(page):
    return [pk for pk, _ in applicant_items(page)]


def expected(data, sort, keep=None):
    """The application IDs of the kept rows, in the agreed order for ``sort``."""
    return [data["rows"][n].pk for n in EXPECTED[sort] if keep is None or n in keep]


def rows_in(opening):
    return {n for n, row in enumerate(ROWS) if row[2] == opening}


def url(**params):
    return "/?" + urlencode({k: v for k, v in params.items() if v})


def sort_links(page):
    """{option: link attributes} for each link in the one #sort-controls."""
    found = re.findall(
        r'<nav\b[^>]*id="sort-controls"[^>]*>(.*?)</nav>', page, re.DOTALL
    )
    assert len(found) == 1, "expected one #sort-controls"
    links = re.findall(r"<a\b([^>]*)>", found[0])
    return {attr(link, "data-sort"): link for link in links}


def link_sort(link):
    """The ``sort`` value a link asks for."""
    match = re.search(r"[?&]sort=([^&]*)", unescape(attr(link, "href")))
    assert match, "sort link has no sort value"
    return match.group(1)


# --- The orders -------------------------------------------------------------


def test_name_is_the_default_order(employee_client, data):
    for query in ("opening=all", "opening=all&sort=", "opening=all&sort=name"):
        assert order(get(employee_client, query)) == expected(data, "name"), query


@pytest.mark.parametrize("sort", SORTS)
def test_each_sort_orders_all_openings(employee_client, data, sort):
    before = snapshot()

    for headers in ({}, HTMX):
        page = get(employee_client, f"opening=all&sort={sort}", **headers)
        assert order(page) == expected(data, sort), sort

    assert snapshot() == before


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("opening", ["analyst", "designer"])
def test_each_sort_orders_a_single_opening(employee_client, data, opening, sort):
    page = get(employee_client, f"opening={data[opening].pk}&sort={sort}")
    assert order(page) == expected(data, sort, rows_in(opening))


def test_stage_sort_is_pipeline_order_not_alphabetical(employee_client, data):
    page = get(employee_client, "opening=all&sort=stage")
    stages = [Application.objects.get(pk=pk).stage for pk in order(page)]
    pipeline = [s.value for s in Stage]

    assert stages == sorted(stages, key=pipeline.index)
    assert stages != sorted(stages)  # alphabetical would put Final Review second


def test_ties_fall_back_to_the_application_id(employee_client, data):
    """Rows 0 and 2 share a name, stage and time: lower ID first, both ways."""
    first, second = data["rows"][0].pk, data["rows"][2].pk
    for sort in ("name", "-name", "stage", "-stage", "updated", "-updated"):
        listed = order(get(employee_client, f"opening=all&sort={sort}"))
        assert listed.index(first) + 1 == listed.index(second), sort


@pytest.mark.parametrize(
    ("query", "rows"),
    [
        ("q=doe&sort=-updated", [0, 2, 1]),
        ("q=doe&sort=opening", [2, 1, 0]),
        ("stage=interview&sort=opening", [2, 0]),
        ("stage=interview&sort=-opening", [0, 2]),
        ("q=doe&stage=interview&sort=-name", [0, 2]),
        ("q=an&sort=-stage", [8, 0, 2]),  # Hana (Hired), then both Anas
    ],
)
def test_sorting_combines_with_search_and_stage(employee_client, data, query, rows):
    page = get(employee_client, f"opening=all&{query}")
    assert order(page) == [data["rows"][n].pk for n in rows]


def test_sorting_combines_with_filters_in_a_single_opening(employee_client, data):
    analyst = data["analyst"].pk
    page = get(employee_client, f"opening={analyst}&q=an&sort=updated")
    assert order(page) == [data["rows"][n].pk for n in (0, 8)]
    page = get(employee_client, f"opening={analyst}&stage=interview&sort=-name")
    assert order(page) == [data["rows"][0].pk]


# --- Counts, Archived, the panel, read-only ---------------------------------


@pytest.mark.parametrize("sort", SORTS)
def test_sorting_keeps_counts_archived_badges_and_the_panel(
    employee_client, data, sort
):
    eve = data["rows"][5]  # archived, Rejected
    unsorted = get(employee_client, f"opening=all&application={eve.pk}")
    before = snapshot()

    page = get(employee_client, f"opening=all&application={eve.pk}&sort={sort}")

    # Same stages and counts; the count links now also carry the sort (Test 3).
    assert {s: c for s, (_, c) in stage_summary(page).items()} == {
        s: c for s, (_, c) in stage_summary(unsorted).items()
    }
    assert list(stage_summary(page)) == [s.value for s in Stage]
    assert total(page) == total(unsorted) == len(ROWS)
    items = dict(applicant_items(page))
    for application in data["rows"]:
        archived = application.candidate.is_archived
        assert (">Archived</span>" in items[application.pk]) is archived
        assert application.opening.title in items[application.pk]
    assert detail_panel(page)[0] == eve.pk
    assert "Brown" in detail_panel(page)[1]
    assert snapshot() == before


@pytest.mark.parametrize(
    "value", ["bogus", "Name", "NAME", "--name", "name-", "-", "+name", "stage,name"]
)
def test_unknown_sort_values_are_400(employee_client, data, value):
    before = snapshot()
    for scope in ("all", str(data["analyst"].pk)):
        for headers in ({}, HTMX):
            response = employee_client.get(f"/?opening={scope}&sort={value}", **headers)
            assert response.status_code == 400, (scope, value)
    assert snapshot() == before


# --- The sort links ---------------------------------------------------------


@pytest.mark.parametrize("current", [None, *SORTS])
def test_sort_links_keep_the_filters_and_reverse_the_active_option(
    employee_client, data, current
):
    scope = str(data["designer"].pk)
    page = get(
        employee_client, url(opening=scope, q="doe", sort=current).removeprefix("/?")
    )
    active = current or "name"

    links = sort_links(page)

    assert list(links) == OPTIONS
    for option, link in links.items():
        is_active = active.lstrip("-") == option
        wanted = REVERSED[active] if is_active else option
        href = url(opening=scope, q="doe", sort=wanted)
        assert unescape(attr(link, "href")) == href, option
        assert unescape(attr(link, "hx-get")) == href, option
        assert attr(link, "hx-target") == "#workspace"
        assert attr(link, "hx-swap") == "outerHTML"
        assert attr(link, "hx-push-url") == "true"
        assert attr(link, "aria-current") == ("true" if is_active else None), option


def test_sort_links_keep_the_stage_filter_and_selected_application(
    employee_client, data
):
    ana = data["rows"][0]
    page = get(
        employee_client,
        url(
            opening="all", application=ana.pk, stage="interview", sort="-updated"
        ).removeprefix("/?"),
    )

    link = sort_links(page)["opening"]

    assert unescape(attr(link, "href")) == url(
        opening="all", application=ana.pk, stage="interview", sort="opening"
    )


def test_following_the_links_sorts_and_clicking_again_reverses(employee_client, data):
    before = snapshot()
    page = get(employee_client, "opening=all")

    for option in OPTIONS:
        for headers in ({}, HTMX):
            link = sort_links(page)[option]
            first = employee_client.get(unescape(attr(link, "href")), **headers)
            assert first.status_code == 200
            once = first.content.decode()
            assert order(once) == expected(data, link_sort(link))

            # Clicking the now-active option asks for the opposite direction.
            again = sort_links(once)[option]
            assert link_sort(again) == REVERSED[link_sort(link)]
            twice = employee_client.get(unescape(attr(again, "href")), **headers)
            twice = twice.content.decode()
            assert order(twice) == expected(data, link_sort(again))
            if headers:
                assert twice.strip().startswith('<div id="workspace"')
                assert "<html" not in twice
            else:
                assert "<html" in twice
                assert twice.count('id="workspace"') == 1

    assert snapshot() == before


def test_sort_links_sit_beside_the_existing_list(employee_client, data):
    page = get(employee_client, "opening=all&sort=stage")

    assert len(sort_links(page)) == len(OPTIONS)
    assert len(applicant_items(page)) == len(ROWS)  # still the #applicant-list
    assert "<table" not in page
