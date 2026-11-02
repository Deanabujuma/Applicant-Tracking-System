"""Phase 7 Test 1: the hiring workspace sidebar."""

import re

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening, OpeningStatus

pytestmark = pytest.mark.django_db

WARNING = "Closed but still has active applicants"


def sidebar_item(page, opening):
    """The sidebar entry for one opening; fails if it's missing or repeated."""
    items = re.findall(
        rf'<li\b[^>]*data-opening="{opening.pk}"[^>]*>(.*?)</li>', page, re.DOTALL
    )
    assert len(items) == 1, f"expected one sidebar entry for {opening}"
    return items[0]


def active_count(item):
    match = re.search(r'title="Active applicants">\s*(\d+)\s*<', item)
    assert match, "no active-applicant count"
    return int(match.group(1))


def test_sidebar_lists_every_opening_with_status_count_and_warning(
    client, django_user_model
):
    employee = django_user_model.objects.create_user(username="jsmith")
    client.force_login(employee)

    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    legacy = JobOpening.objects.create(
        title="Legacy Support", department="IT", status=OpeningStatus.CLOSED
    )
    retired = JobOpening.objects.create(
        title="Retired Role", department="Ops", status=OpeningStatus.CLOSED
    )
    empty = JobOpening.objects.create(title="New Role", department="HR")
    stages = {
        analyst: [Stage.APPLIED, Stage.SCREENING, Stage.HIRED],  # 2 active
        legacy: [Stage.INTERVIEW, Stage.OFFER, Stage.REJECTED],  # 2 active, Closed
        retired: [Stage.HIRED, Stage.WITHDRAWN, Stage.REJECTED],  # 0 active, Closed
        empty: [],
    }
    n = 0
    for opening, opening_stages in stages.items():
        for stage in opening_stages:
            n += 1
            candidate = Candidate.objects.create(
                first_name=f"Person{n}",
                last_name="Doe",
                email=f"person{n}@example.com",
                source=Source.REFERRAL,
            )
            Application.objects.create(
                candidate=candidate,
                opening=opening,
                stage=stage,
                stage_changed_by=employee,
            )
    apps_before = list(Application.objects.order_by("pk").values())
    openings_before = list(JobOpening.objects.order_by("pk").values())

    response = client.get("/")
    assert response.status_code == 200
    page = response.content.decode()

    # An All Openings entry.
    assert re.search(r'<a\b[^>]*href="/\?opening=all"[^>]*>\s*All Openings', page)

    # Every opening: title, department, status, link, and active-applicant count.
    expected = {
        analyst: ("Open", 2, False),
        legacy: ("Closed", 2, True),
        retired: ("Closed", 0, False),
        empty: ("Open", 0, False),
    }
    for opening, (status, count, flagged) in expected.items():
        item = sidebar_item(page, opening)
        assert opening.title in item
        assert opening.department in item
        assert status in item
        assert f'href="/?opening={opening.pk}"' in item
        assert active_count(item) == count, opening.title
        assert (WARNING in item) is flagged, opening.title

    # The same warning on the flagged opening's own page, and only there.
    for opening, (_, _, flagged) in expected.items():
        detail = client.get(f"/openings/{opening.pk}/").content.decode()
        has_warning = bool(
            re.search(rf'class="alert alert-warning"[^>]*>[^<]*{WARNING}', detail)
        )
        assert has_warning is flagged, opening.title

    # Viewing the workspace changed nothing.
    assert list(Application.objects.order_by("pk").values()) == apps_before
    assert list(JobOpening.objects.order_by("pk").values()) == openings_before
