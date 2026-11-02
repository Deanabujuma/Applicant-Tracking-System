"""Phase 7 regression tests: workspace access, parameters, HTMX, and empty states."""

import re
from html import unescape

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from hiring.tests.test_workspace_detail import detail_panel, row_link
from hiring.tests.test_workspace_selection import (
    HTMX,
    applicant_items,
    attr,
    stage_summary,
    total,
)
from openings.models import JobOpening, OpeningStatus

pytestmark = pytest.mark.django_db

RESTORE = {**HTMX, "HTTP_HX_HISTORY_RESTORE_REQUEST": "true"}
WARNING = "Closed but still has active applicants"


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def data(employee):
    """Extra candidates first, so candidate and application IDs differ."""
    for n in range(3):
        Candidate.objects.create(
            first_name=f"Spare{n}",
            last_name="Nobody",
            email=f"spare{n}@example.com",
            source=Source.OTHER,
        )
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    legacy = JobOpening.objects.create(
        title="Legacy Support", department="IT", status=OpeningStatus.CLOSED
    )
    retired = JobOpening.objects.create(
        title="Retired Role", department="Ops", status=OpeningStatus.CLOSED
    )
    empty = JobOpening.objects.create(title="New Role", department="HR")
    ana = Candidate.objects.create(
        first_name="Ana",
        last_name="Zimmer",
        email="ana@example.com",
        source=Source.REFERRAL,
    )
    fay = Candidate.objects.create(
        first_name="Fay",
        last_name="Usher",
        email="fay@example.com",
        source=Source.JOB_BOARD,
        is_archived=True,
    )

    def apply(candidate, opening, stage):
        return Application.objects.create(
            candidate=candidate, opening=opening, stage=stage, stage_changed_by=employee
        )

    return {
        "analyst": analyst,
        "legacy": legacy,
        "retired": retired,
        "empty": empty,
        "ana_analyst": apply(ana, analyst, Stage.SCREENING),
        "ana_legacy": apply(ana, legacy, Stage.INTERVIEW),
        "fay_analyst": apply(fay, analyst, Stage.HIRED),
        "fay_retired": apply(fay, retired, Stage.REJECTED),
    }


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
    )


def valid_urls(data):
    analyst = data["analyst"].pk
    return [
        "/",
        "/?opening=all",
        f"/?opening={analyst}",
        f"/?opening={data['empty'].pk}",
        f"/?application={data['fay_retired'].pk}",
        f"/?opening=all&application={data['ana_legacy'].pk}",
        f"/?opening={analyst}&application={data['fay_analyst'].pk}",
    ]


# --- Access -----------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_anonymous_visitors_are_sent_to_login(client, data, headers):
    before = snapshot()
    for url in valid_urls(data):
        response = client.get(url, **headers)
        assert response.status_code == 302, url
        assert response.url.startswith("/accounts/login/?next="), url
    assert snapshot() == before


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_deactivated_employees_are_sent_to_login(client, employee, data, headers):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    before = snapshot()

    for url in valid_urls(data):
        response = client.get(url, **headers)
        assert response.status_code == 302, url
        assert response.url.startswith("/accounts/login/"), url
    assert snapshot() == before


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_workspace_is_get_only(employee_client, data, method):
    before = snapshot()

    response = getattr(employee_client, method)(f"/?opening={data['analyst'].pk}")

    assert response.status_code == 405
    assert snapshot() == before


# --- Parameters -------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "opening=",
        "opening=abc",
        "opening=1.5",
        "opening=ALL",
        "opening=%C2%B2",  # a superscript two: a digit, but not an integer
        "opening=all&application=",
        "opening=all&application=abc",
        "application=x1",
    ],
)
def test_malformed_parameters_are_400(employee_client, data, query):
    before = snapshot()
    for headers in ({}, HTMX):
        assert employee_client.get(f"/?{query}", **headers).status_code == 400, query
    assert snapshot() == before


def test_nonexistent_records_and_other_openings_applications_are_404(
    employee_client, data
):
    analyst, empty = data["analyst"], data["empty"]
    missing_opening = JobOpening.objects.order_by("-pk").first().pk + 1
    missing_app = Application.objects.order_by("-pk").first().pk + 1
    ana_id = data["ana_analyst"].candidate_id
    assert not data["analyst"].applications.filter(pk=ana_id).exists()
    before = snapshot()

    for url in [
        f"/?opening={missing_opening}",
        "/?opening=-1",
        f"/?opening=all&application={missing_app}",
        f"/?opening={analyst.pk}&application={missing_app}",
        f"/?opening={analyst.pk}&application={data['ana_legacy'].pk}",
        f"/?opening={empty.pk}&application={data['ana_analyst'].pk}",
        # The candidate's ID is not an application ID in this scope.
        f"/?opening={analyst.pk}&application={ana_id}",
    ]:
        for headers in ({}, HTMX):
            response = employee_client.get(url, **headers)
            assert response.status_code == 404, url
            assert detail_panel(response.content.decode()) is None
    assert snapshot() == before


# --- Full page, partial, and Vary -------------------------------------------


@pytest.mark.parametrize(
    ("headers", "full"),
    [({}, True), (HTMX, False), (RESTORE, True)],
    ids=["page", "htmx", "history-restore"],
)
def test_full_page_or_partial_with_vary_header(employee_client, data, headers, full):
    for url in valid_urls(data):
        response = employee_client.get(url, **headers)
        assert response.status_code == 200, url
        page = response.content.decode()

        assert ("<html" in page) is full, url
        assert ("<header" in page) is full, url
        if not full:
            assert page.strip().startswith('<div id="workspace"'), url

        vary = {v.strip().lower() for v in response.headers["Vary"].split(",")}
        assert {"hx-request", "hx-history-restore-request"} <= vary, url


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_single_workspace_summary_and_panel(employee_client, data, headers):
    for url in valid_urls(data):
        page = employee_client.get(url, **headers).content.decode()
        assert page.count('id="workspace"') == 1, url
        assert page.count('id="openings-sidebar"') == 1, url
        assert page.count('id="stage-summary"') == 1, url
        assert page.count('id="applicant-list"') == 1, url
        assert page.count('id="application-detail"') == ("application=" in url), url


# --- Empty states -----------------------------------------------------------


def assert_all_zero(page):
    summary = stage_summary(page)
    assert list(summary) == [stage.value for stage in Stage]
    for stage in Stage:
        item, count = summary[stage.value]
        assert stage.label in item
        assert count == 0
    assert total(page) == 0
    assert applicant_items(page) == []
    assert "No applications yet." in page


def test_empty_database_shows_all_openings_and_empty_states(employee_client):
    for url in ("/", "/?opening=all"):
        response = employee_client.get(url)
        assert response.status_code == 200
        page = response.content.decode()
        assert re.search(r"<h1\b[^>]*>\s*All Openings\s*</h1>", page)
        assert "No openings yet." in page
        assert_all_zero(page)
        assert detail_panel(page) is None


def test_opening_without_applications_shows_zero_counts(employee_client, data):
    for headers in ({}, HTMX):
        page = employee_client.get(
            f"/?opening={data['empty'].pk}", **headers
        ).content.decode()
        assert re.search(r"<h1\b[^>]*>\s*New Role\s*</h1>", page)
        assert_all_zero(page)


# --- Rows, archived badge, and the detail panel -----------------------------


def test_rows_link_to_application_ids_not_candidate_ids(employee_client, data):
    for scope in ("all", str(data["analyst"].pk)):
        page = employee_client.get(f"/?opening={scope}").content.decode()
        items = applicant_items(page)
        assert items
        for pk, item in items:
            application = Application.objects.get(pk=pk)
            assert application.candidate_id != pk  # the fixture keeps them apart
            href = unescape(attr(row_link(item), "href"))
            assert href == f"/?opening={scope}&application={pk}"
            assert len(re.findall(r"<a\b", item)) == 1


def test_archived_candidates_applications_stay_visible_with_badge(
    employee_client, data
):
    fay_apps = {data["fay_analyst"].pk, data["fay_retired"].pk}
    for scope, expected in (
        ("all", fay_apps),
        (str(data["analyst"].pk), {data["fay_analyst"].pk}),
        (str(data["retired"].pk), {data["fay_retired"].pk}),
    ):
        page = employee_client.get(f"/?opening={scope}").content.decode()
        items = dict(applicant_items(page))
        assert expected <= set(items)
        for pk, item in items.items():
            archived = pk in fay_apps
            assert (">Archived</span>" in item) is archived, (scope, pk)
            assert item.count(">Archived</span>") == int(archived)

    page = employee_client.get(
        f"/?opening=all&application={data['fay_retired'].pk}"
    ).content.decode()
    _, panel = detail_panel(page)
    assert panel.count(">Archived</span>") == 1


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_detail_panel_and_partial_have_no_mutation_controls(
    employee_client, data, headers
):
    for application in (data["ana_analyst"], data["fay_analyst"]):
        url = f"/?opening=all&application={application.pk}"
        page = employee_client.get(url, **headers).content.decode()
        _, panel = detail_panel(page)
        for forbidden in ("<form", "<button", "<input", "<select", "hx-post"):
            assert forbidden not in panel, forbidden
        # Phase 8 adds move actions (GET links to a confirmation) for active
        # stages only; Hired still has none, and Undo waits for Phase 9.
        assert "Undo" not in panel
        if application.stage == Stage.HIRED:
            for word in ("Move", "Confirm", "data-move-to"):
                assert word not in panel, word
        # Besides the header's Log out (full page only), the one other form is
        # Phase 10's search, a GET form outside the panel.
        assert len(re.findall(r"<form\b", page)) == (1 if headers else 2)
        assert len(re.findall(r'<form\b[^>]*id="workspace-search"', page)) == 1
        assert re.search(r'<form\b[^>]*id="workspace-search"[^>]*method="get"', page)


# --- No mutation and sidebar consistency ------------------------------------


def test_workspace_requests_never_change_records(employee_client, data):
    before = snapshot()

    for url in valid_urls(data):
        for headers in ({}, HTMX, RESTORE):
            for _ in range(2):
                employee_client.get(url, **headers)
    for bad in ("/?opening=abc", "/?opening=99999", "/?opening=all&application=x"):
        employee_client.get(bad)

    assert snapshot() == before  # every field, including timestamps


def sidebar_entry(page, opening):
    return re.search(
        rf'<li\b[^>]*data-opening="{opening.pk}"[^>]*>(.*?)</li>', page, re.DOTALL
    ).group(1)


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_sidebar_counts_and_warnings_hold_in_every_view(employee_client, data, headers):
    expected = {
        # opening: (active count, warned)
        "analyst": (1, False),  # Screening; Hired not counted
        "legacy": (1, True),  # Closed with Interview
        "retired": (0, False),  # Closed, only Rejected
        "empty": (0, False),
    }
    for url in valid_urls(data):
        page = employee_client.get(url, **headers).content.decode()
        for name, (count, warned) in expected.items():
            item = sidebar_entry(page, data[name])
            match = re.search(r'title="Active applicants">\s*(\d+)\s*<', item)
            assert int(match.group(1)) == count, (url, name)
            assert (WARNING in item) is warned, (url, name)
