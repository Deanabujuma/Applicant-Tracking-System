"""Phase 5 regression tests: applications, protected deletes, and app boundaries."""

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils.html import escape

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening, OpeningStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


def make_candidate(first, *, archived=False):
    return Candidate.objects.create(
        first_name=first,
        last_name="Doe",
        email=f"{first.lower()}@example.com",
        source=Source.REFERRAL,
        is_archived=archived,
    )


def make_opening(title, *, status=OpeningStatus.OPEN):
    return JobOpening.objects.create(title=title, department="IT", status=status)


def apply(candidate, opening, employee, **extra):
    return Application.objects.create(
        candidate=candidate, opening=opening, stage_changed_by=employee, **extra
    )


def alerts(page):
    """(alert class, text) for every message alert on a rendered page."""
    return re.findall(r'<div role="alert" class="alert (alert-\w+)">(.*?)</div>', page)


# --- Model and database rules -----------------------------------------------


def test_database_rejects_duplicate_application_when_form_is_bypassed(employee):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")
    apply(jane, analyst, employee)

    with pytest.raises(IntegrityError), transaction.atomic():
        apply(jane, analyst, employee)

    assert Application.objects.count() == 1


def test_one_candidate_can_apply_to_several_openings(employee_client, employee):
    jane = make_candidate("Jane")
    openings = [make_opening(t) for t in ("Analyst", "Engineer", "Designer")]

    for opening in openings:
        response = employee_client.post(
            f"/applications/new/?candidate={jane.pk}", {"opening": opening.pk}
        )
        assert response.status_code == 302

    assert {a.opening for a in jane.applications.all()} == set(openings)
    assert set(jane.applications.values_list("stage", flat=True)) == {Stage.APPLIED}


def test_closing_an_opening_leaves_its_applications_unchanged(
    employee_client, employee
):
    analyst = make_opening("Analyst")
    apps = [
        apply(make_candidate("Jane"), analyst, employee),
        apply(make_candidate("Bob"), analyst, employee, stage=Stage.INTERVIEW),
    ]
    before = list(Application.objects.order_by("pk").values())

    response = employee_client.post(f"/openings/{analyst.pk}/close/")

    assert response.status_code == 302
    assert JobOpening.objects.get(pk=analyst.pk).status == OpeningStatus.CLOSED
    assert list(Application.objects.order_by("pk").values()) == before
    assert len(before) == len(apps)


# --- Application creation ---------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["", "?candidate=1&opening=1", "?candidate=abc", "?opening=", "?other=1"],
    ids=["missing", "both", "not-a-number", "empty", "unknown-param"],
)
@pytest.mark.parametrize("method", ["get", "post"])
def test_malformed_application_urls_are_rejected(employee_client, query, method):
    make_candidate("Jane")
    make_opening("Analyst")

    response = getattr(employee_client, method)(f"/applications/new/{query}")

    assert response.status_code == 400
    assert Application.objects.count() == 0


@pytest.mark.parametrize("query", ["?candidate=999", "?opening=999"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_nonexistent_fixed_record_is_404(employee_client, query, method):
    response = getattr(employee_client, method)(f"/applications/new/{query}")

    assert response.status_code == 404
    assert Application.objects.count() == 0


@pytest.mark.parametrize("method", ["get", "post"])
def test_application_creation_requires_login(client, method):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")
    url = f"/applications/new/?candidate={jane.pk}"

    response = getattr(client, method)(url, {"opening": analyst.pk})

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/?next=/applications/new/")
    assert Application.objects.count() == 0


def test_deactivated_employee_cannot_create_applications(client, employee):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")

    response = client.post(
        f"/applications/new/?candidate={jane.pk}", {"opening": analyst.pk}
    )

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert Application.objects.count() == 0


@pytest.fixture
def csrf_client(employee):
    client = Client(enforce_csrf_checks=True)
    client.force_login(employee)
    return client


def test_application_creation_requires_csrf_token(csrf_client):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")
    url = f"/applications/new/?candidate={jane.pk}"

    assert csrf_client.post(url, {"opening": analyst.pk}).status_code == 403
    assert Application.objects.count() == 0

    page = csrf_client.get(url).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    response = csrf_client.post(
        url, {"opening": analyst.pk, "csrfmiddlewaretoken": token}
    )
    assert response.status_code == 302
    assert Application.objects.count() == 1


@pytest.mark.parametrize("side", ["candidate", "opening"])
def test_success_message_is_shown_once_on_the_starting_page(employee_client, side):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")
    fixed, chosen = (jane, analyst) if side == "candidate" else (analyst, jane)
    other_side = "opening" if side == "candidate" else "candidate"

    response = employee_client.post(
        f"/applications/new/?{side}={fixed.pk}", {other_side: chosen.pk}, follow=True
    )

    assert response.redirect_chain == [(fixed.get_absolute_url(), 302)]
    expected = (
        f"Added application: Jane Doe → #{analyst.pk} Analyst. It starts in Applied."
    )
    assert alerts(response.content.decode()) == [("alert-success", escape(expected))]
    again = employee_client.get(fixed.get_absolute_url()).content.decode()
    assert alerts(again) == []


def test_application_links_hidden_for_archived_candidates_and_closed_openings(
    employee_client,
):
    active, archived = make_candidate("Jane"), make_candidate("Ann", archived=True)
    open_, closed = (
        make_opening("Analyst"),
        make_opening("Legacy", status=OpeningStatus.CLOSED),
    )

    def page(record):
        return employee_client.get(record.get_absolute_url()).content.decode()

    assert f'href="/applications/new/?candidate={active.pk}"' in page(active)
    assert "/applications/new/" not in page(archived)
    assert f'href="/applications/new/?opening={open_.pk}"' in page(open_)
    assert "/applications/new/" not in page(closed)


# --- Candidate deletion -----------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
def test_candidate_delete_requires_login(client, method):
    jane = make_candidate("Jane")
    url = f"/candidates/{jane.pk}/delete/"

    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={url}"
    assert Candidate.objects.filter(pk=jane.pk).exists()


def test_deactivated_employee_cannot_delete_candidates(client, employee):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    jane = make_candidate("Jane")

    response = client.post(f"/candidates/{jane.pk}/delete/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert Candidate.objects.filter(pk=jane.pk).exists()


@pytest.mark.parametrize("method", ["get", "post"])
def test_candidate_delete_of_nonexistent_candidate_is_404(employee_client, method):
    jane = make_candidate("Jane")

    response = getattr(employee_client, method)(f"/candidates/{jane.pk + 999}/delete/")

    assert response.status_code == 404
    assert Candidate.objects.filter(pk=jane.pk).exists()


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_candidate_delete_rejects_other_methods(employee_client, method):
    jane = make_candidate("Jane")

    response = getattr(employee_client, method)(f"/candidates/{jane.pk}/delete/")

    assert response.status_code == 405
    assert Candidate.objects.filter(pk=jane.pk).exists()


def test_candidate_delete_requires_csrf_token(csrf_client):
    jane = make_candidate("Jane")
    url = f"/candidates/{jane.pk}/delete/"

    assert csrf_client.post(url).status_code == 403
    assert Candidate.objects.filter(pk=jane.pk).exists()

    page = csrf_client.get(url).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    assert csrf_client.post(url, {"csrfmiddlewaretoken": token}).status_code == 302
    assert not Candidate.objects.filter(pk=jane.pk).exists()


def test_deleting_candidate_without_applications_shows_message_once(employee_client):
    jane, bob = make_candidate("Jane"), make_candidate("Bob")

    response = employee_client.post(f"/candidates/{jane.pk}/delete/", follow=True)

    assert response.redirect_chain == [("/candidates/", 302)]
    assert alerts(response.content.decode()) == [
        ("alert-success", "Deleted candidate Jane Doe.")
    ]
    assert list(Candidate.objects.all()) == [bob]
    assert alerts(employee_client.get("/candidates/").content.decode()) == []


def test_refused_delete_errors_are_shown_once(employee_client, employee):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")
    apply(jane, analyst, employee)
    opening_refused = (
        f"Opening #{analyst.pk} Analyst has applications, so it can't be "
        "deleted. Close it instead."
    )
    cases = [
        (
            f"/openings/{analyst.pk}/",
            opening_refused,
        ),
        (
            f"/candidates/{jane.pk}/",
            "Jane Doe has applications, so they can't be deleted.",
        ),
    ]

    for detail_url, message in cases:
        response = employee_client.post(f"{detail_url}delete/", follow=True)
        assert alerts(response.content.decode()) == [("alert-error", escape(message))]
        assert alerts(employee_client.get(detail_url).content.decode()) == []

    assert Application.objects.count() == 1


# --- Read-only Applications lists -------------------------------------------


def applications_section(page):
    match = re.search(r'id="applications"[^>]*>(.*?)</(?:ul|p)>', page, re.DOTALL)
    assert match, "no Applications section"
    return match.group(1)


def test_detail_pages_list_applications_with_links_and_stages(
    employee_client, employee
):
    jane, bob = make_candidate("Jane"), make_candidate("Bob")
    analyst, engineer = make_opening("Analyst"), make_opening("Engineer")
    apply(jane, analyst, employee)
    apply(jane, engineer, employee, stage=Stage.INTERVIEW)
    apply(bob, analyst, employee, stage=Stage.OFFER)

    section = applications_section(
        employee_client.get(f"/candidates/{jane.pk}/").content.decode()
    )
    assert f'href="/openings/{analyst.pk}/"' in section
    assert f'href="/openings/{engineer.pk}/"' in section
    assert ">Applied<" in section
    assert ">Interview<" in section
    assert "Bob" not in section

    section = applications_section(
        employee_client.get(f"/openings/{analyst.pk}/").content.decode()
    )
    assert f'href="/candidates/{jane.pk}/"' in section
    assert f'href="/candidates/{bob.pk}/"' in section
    assert ">Applied<" in section
    assert ">Offer<" in section
    assert "Engineer" not in section

    # Read-only: no forms or stage controls inside the lists.
    assert "<form" not in section
    assert "<select" not in section


def test_detail_pages_show_empty_state_without_applications(employee_client):
    jane, analyst = make_candidate("Jane"), make_opening("Analyst")

    for url in (f"/candidates/{jane.pk}/", f"/openings/{analyst.pk}/"):
        page = employee_client.get(url).content.decode()
        assert "No applications yet." in applications_section(page)


# --- App boundaries ---------------------------------------------------------


@pytest.mark.parametrize("app", ["candidates", "openings"])
def test_app_never_imports_hiring(app):
    """The dependency is one-way: hiring imports candidates/openings, never back."""
    offenders = []
    for path in sorted((Path(settings.BASE_DIR) / app).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "hiring" or n.startswith("hiring.") for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
