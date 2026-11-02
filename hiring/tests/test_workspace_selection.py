"""Phase 7 Test 2: opening selection, stage summary, applicant list, and HTMX."""

import re

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening, OpeningStatus

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


def block(page, element_id):
    """The inner HTML of the one <ul> with this id."""
    found = re.findall(rf'<ul\b[^>]*id="{element_id}"[^>]*>(.*?)</ul>', page, re.DOTALL)
    assert len(found) == 1, f"expected one #{element_id}"
    return found[0]


def stage_summary(page):
    """{stage value: (item html, count)} in page order, from #stage-summary."""
    summary = {}
    for value, item in re.findall(
        r'<li\b[^>]*data-stage="(\w+)"[^>]*>(.*?)</li>',
        block(page, "stage-summary"),
        re.DOTALL,
    ):
        counts = re.findall(r">\s*(\d+)\s*<", item)
        assert len(counts) == 1, f"expected one count for {value}"
        summary[value] = (item, int(counts[0]))
    return summary


def total(page):
    match = re.search(r'id="application-total"[^>]*>\s*(\d+)', page)
    assert match, "no application total"
    return int(match.group(1))


def applicant_items(page):
    """[(application pk, item html)] in page order, from #applicant-list."""
    return [
        (int(pk), item)
        for pk, item in re.findall(
            r'<li\b[^>]*data-application="(\d+)"[^>]*>(.*?)</li>',
            block(page, "applicant-list"),
            re.DOTALL,
        )
    ]


def sidebar_links(page):
    """The attribute text of every <a> in the openings sidebar."""
    return re.findall(r"<a\b([^>]*)>", block(page, "openings-sidebar"))


def attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return match.group(1) if match else None


def current_hrefs(page):
    return [
        attr(tag, "href")
        for tag in sidebar_links(page)
        if attr(tag, "aria-current") == "page"
    ]


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def data(employee):
    """Two openings; Ana applied to both; Fay is archived with a Hired application."""
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    designer = JobOpening.objects.create(
        title="Designer", department="Marketing", status=OpeningStatus.CLOSED
    )
    rows = [
        # (first, last, archived, opening, stage)
        ("Ana", "Zimmer", False, analyst, Stage.APPLIED),
        ("Ben", "Young", False, analyst, Stage.APPLIED),
        ("Cara", "Xu", False, analyst, Stage.SCREENING),
        ("Dev", "Wong", False, analyst, Stage.INTERVIEW),
        ("Eli", "Vance", False, analyst, Stage.OFFER),
        ("Fay", "Usher", True, analyst, Stage.HIRED),
        ("Gus", "Tate", False, analyst, Stage.REJECTED),
        ("Hal", "Stone", False, analyst, Stage.WITHDRAWN),
        ("Ana", "Zimmer", False, designer, Stage.FINAL_REVIEW),
        ("Ivy", "Ross", False, designer, Stage.APPLIED),
    ]
    apps = {}
    for first, last, archived, opening, stage in rows:
        candidate, _ = Candidate.objects.get_or_create(
            email=f"{first.lower()}@example.com",
            defaults={
                "first_name": first,
                "last_name": last,
                "source": Source.REFERRAL,
                "is_archived": archived,
            },
        )
        apps[(first, opening.title)] = Application.objects.create(
            candidate=candidate, opening=opening, stage=stage, stage_changed_by=employee
        )
    return {"analyst": analyst, "designer": designer, "apps": apps}


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
    )


def test_selected_opening_shows_all_stage_counts_and_only_its_applicants(
    employee_client, data
):
    analyst, apps = data["analyst"], data["apps"]
    before = snapshot()

    response = employee_client.get(f"/?opening={analyst.pk}")
    assert response.status_code == 200
    page = response.content.decode()

    # The opening is the selected sidebar entry.
    assert current_hrefs(page) == [f"/?opening={analyst.pk}"]

    # All eight stages, in order, with labels and counts (completed ones too).
    summary = stage_summary(page)
    assert list(summary) == [stage.value for stage in Stage]
    expected = {
        Stage.APPLIED: 2,
        Stage.SCREENING: 1,
        Stage.INTERVIEW: 1,
        Stage.FINAL_REVIEW: 0,
        Stage.OFFER: 1,
        Stage.HIRED: 1,
        Stage.REJECTED: 1,
        Stage.WITHDRAWN: 1,
    }
    for stage, count in expected.items():
        item, shown = summary[stage.value]
        assert stage.label in item
        assert shown == count, stage.label
    assert total(page) == 8

    # The sidebar still counts only active applicants for this opening.
    analyst_link = re.search(
        rf'<li\b[^>]*data-opening="{analyst.pk}"[^>]*>(.*?)</li>', page, re.DOTALL
    ).group(1)
    assert re.search(r'title="Active applicants">\s*5\s*<', analyst_link)

    # Only this opening's applications, ordered by last then first name.
    items = applicant_items(page)
    ordered = ["Hal", "Gus", "Fay", "Eli", "Dev", "Cara", "Ben", "Ana"]
    assert [pk for pk, _ in items] == [
        apps[(first, "Data Analyst")].pk for first in ordered
    ]
    for pk, item in items:
        application = Application.objects.get(pk=pk)
        assert str(application.candidate) in item
        assert application.get_stage_display() in item
        assert (">Archived<" in item) is application.candidate.is_archived

    assert snapshot() == before


@pytest.mark.parametrize("url", ["/", "/?opening=all"])
def test_all_openings_lists_every_application_with_job_title(
    employee_client, data, url
):
    before = snapshot()

    page = employee_client.get(url).content.decode()

    # All Openings is selected (and is the default for "/").
    assert current_hrefs(page) == ["/?opening=all"]

    summary = stage_summary(page)
    assert list(summary) == [stage.value for stage in Stage]
    assert summary[Stage.APPLIED.value][1] == 3
    assert summary[Stage.FINAL_REVIEW.value][1] == 1
    assert total(page) == 10

    items = dict(applicant_items(page))
    assert set(items) == {app.pk for app in data["apps"].values()}
    for (first, title), application in data["apps"].items():
        item = items[application.pk]
        assert first in item
        assert title in item  # each applicant's job title
        assert application.get_stage_display() in item
        assert (">Archived<" in item) is (first == "Fay")

    assert snapshot() == before


def test_htmx_navigation_returns_the_partial_with_link_fallbacks(employee_client, data):
    analyst = data["analyst"]
    url = f"/?opening={analyst.pk}"
    before = snapshot()

    # A normal GET is the whole page containing the workspace once.
    full = employee_client.get(url).content.decode()
    assert "<html" in full
    assert full.count('id="workspace"') == 1

    # An HTMX GET is just the reusable partial.
    partial = employee_client.get(url, **HTMX).content.decode().strip()
    assert partial.startswith('<div id="workspace"')
    assert "<html" not in partial
    assert "<header" not in partial
    assert current_hrefs(partial) == [url]
    assert total(partial) == 8

    # A history restore (back button with no cache) needs the whole page.
    restore = employee_client.get(
        url, HTTP_HX_HISTORY_RESTORE_REQUEST="true", **HTMX
    ).content.decode()
    assert "<html" in restore

    # Every sidebar link: real href fallback plus the HTMX swap of #workspace.
    links = sidebar_links(full)
    assert {attr(tag, "href") for tag in links} == {
        "/?opening=all",
        f"/?opening={analyst.pk}",
        f"/?opening={data['designer'].pk}",
    }
    for tag in links:
        assert attr(tag, "hx-get") == attr(tag, "href")
        assert attr(tag, "hx-target") == "#workspace"
        assert attr(tag, "hx-swap") == "outerHTML"  # replace, not nest
        assert attr(tag, "hx-push-url") == "true"

    assert snapshot() == before
