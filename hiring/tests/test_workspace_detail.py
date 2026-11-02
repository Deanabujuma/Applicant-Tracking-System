"""Phase 7 Test 3: the read-only applicant detail panel in the workspace."""

import re
from html import unescape

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
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


def detail_panel(page):
    """(selected application pk, panel html), or None when nothing is selected."""
    found = re.findall(
        r'<aside\b[^>]*id="application-detail"[^>]*data-selected="(\d+)"[^>]*>'
        r"(.*?)</aside>",
        page,
        re.DOTALL,
    )
    assert len(found) <= 1, "more than one detail panel"
    return (int(found[0][0]), found[0][1]) if found else None


def row_link(item):
    """The attributes of the applicant row's link."""
    match = re.search(r"<a\b([^>]*)>", item)
    assert match, "applicant row has no link"
    return match.group(1)


def field(panel, label):
    """The <dd> that follows the <dt> with this label."""
    match = re.search(
        rf"<dt\b[^>]*>\s*{label}\s*</dt>\s*<dd\b[^>]*>(.*?)</dd>", panel, re.DOTALL
    )
    assert match, f"no {label} in the detail panel"
    return match.group(1)


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def data(employee):
    """Ana applied to both openings; Fay (archived) was hired as an analyst."""
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    designer = JobOpening.objects.create(title="Designer", department="Marketing")
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
        "designer": designer,
        "ana_analyst": apply(ana, analyst, Stage.APPLIED),
        "ana_designer": apply(ana, designer, Stage.FINAL_REVIEW),
        "fay_analyst": apply(fay, analyst, Stage.HIRED),
    }


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
    )


def assert_read_only(panel):
    assert "<form" not in panel
    assert "<button" not in panel
    assert 'method="post"' not in panel.lower()
    assert "hx-post" not in panel
    assert "Undo" not in panel


def test_applicant_rows_link_to_their_own_application_in_the_current_scope(
    employee_client, data
):
    analyst = data["analyst"]
    for scope, expected in (
        ("all", {data["ana_analyst"], data["ana_designer"], data["fay_analyst"]}),
        (str(analyst.pk), {data["ana_analyst"], data["fay_analyst"]}),
    ):
        page = employee_client.get(f"/?opening={scope}").content.decode()
        items = dict(applicant_items(page))
        assert set(items) == {app.pk for app in expected}
        assert detail_panel(page) is None  # nothing selected yet
        for pk, item in items.items():
            link = row_link(item)
            url = f"/?opening={scope}&application={pk}"
            assert unescape(attr(link, "href")) == url
            assert unescape(attr(link, "hx-get")) == url
            assert attr(link, "hx-target") == "#workspace"
            assert attr(link, "hx-swap") == "outerHTML"
            assert attr(link, "hx-push-url") == "true"


def test_selecting_an_application_shows_its_read_only_details(employee_client, data):
    analyst, designer = data["analyst"], data["designer"]
    before = snapshot()

    cases = [
        # (scope, application, opening title, stage, source, archived)
        ("all", data["ana_designer"], "Designer", "Final Review", "Referral", False),
        ("all", data["ana_analyst"], "Data Analyst", "Applied", "Referral", False),
        (analyst.pk, data["ana_analyst"], "Data Analyst", "Applied", "Referral", False),
        (analyst.pk, data["fay_analyst"], "Data Analyst", "Hired", "Job Board", True),
        (
            designer.pk,
            data["ana_designer"],
            "Designer",
            "Final Review",
            "Referral",
            False,
        ),
    ]
    for scope, application, title, stage, source, archived in cases:
        url = f"/?opening={scope}&application={application.pk}"
        candidate = application.candidate
        for headers in ({}, HTMX):
            response = employee_client.get(url, **headers)
            assert response.status_code == 200, url
            page = response.content.decode()
            assert ("<html" in page) is (not headers), url  # full page or partial

            # The panel shows this exact application, not just the candidate.
            selected = detail_panel(page)
            assert selected is not None, url
            pk, panel = selected
            assert pk == application.pk
            assert str(candidate) in field(panel, "Name")
            assert candidate.email in field(panel, "Email")
            assert source in field(panel, "Source")
            assert title in field(panel, "Opening")
            assert stage in field(panel, "Stage")
            assert ("Archived" in panel) is archived
            assert_read_only(panel)

            # The scope, sidebar, counts and list are unchanged by selecting.
            assert current_hrefs(page) == [f"/?opening={scope}"]
            scoped = Application.objects.all()
            if scope != "all":
                scoped = scoped.filter(opening_id=scope)
            assert total(page) == scoped.count()
            assert len(stage_summary(page)) == len(Stage)
            items = dict(applicant_items(page))
            assert set(items) == set(scoped.values_list("pk", flat=True))

            # Exactly the selected row is marked current.
            marked = [
                row
                for row, item in items.items()
                if attr(row_link(item), "aria-current") == "true"
            ]
            assert marked == [application.pk]

    assert snapshot() == before  # including every timestamp


def test_an_application_from_another_opening_is_never_selected(employee_client, data):
    before = snapshot()

    # Ana's Designer application, asked for under Data Analyst.
    url = f"/?opening={data['analyst'].pk}&application={data['ana_designer'].pk}"
    for headers in ({}, HTMX):
        response = employee_client.get(url, **headers)
        assert response.status_code == 404
        assert detail_panel(response.content.decode()) is None

    assert snapshot() == before
