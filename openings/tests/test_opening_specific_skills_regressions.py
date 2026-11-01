"""Regression tests for opening-specific skills (second change, 2026-11-01)."""

import re

import pytest
from django.test import Client

from openings.models import JobOpening, Skill

from .test_opening_specific_skills import (
    assigned_skill_names,
    full_state,
    submitted_skill_ids,
)

pytestmark = pytest.mark.django_db

ADD_URL = "/openings/skills/new/"
REMOVE_URL = "/openings/skills/remove/"


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
def two_openings():
    """Opening #1 has Python and Excel; Opening #2 has Python and SQL."""
    python, excel, sql = (
        Skill.objects.create(name=name) for name in ("Python", "Excel", "SQL")
    )
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    analyst.skills.set([python, excel])
    backend = JobOpening.objects.create(title="Backend Developer", department="IT")
    backend.skills.set([python, sql])
    return analyst, backend, python, excel, sql


def htmx_post(client, url, data):
    return client.post(url, data, HTTP_HX_REQUEST="true")


def requests_for(python, excel):
    """One request of each kind, as (url, data)."""
    return [
        (ADD_URL, {"new_skill_name": "Kubernetes", "skills": [python.pk]}),
        (REMOVE_URL, {"remove_skill": python.pk, "skills": [python.pk, excel.pk]}),
    ]


# --- Access -----------------------------------------------------------------


@pytest.mark.parametrize("which", [0, 1], ids=["add", "remove"])
def test_anonymous_requests_go_to_login_and_change_nothing(client, two_openings, which):
    analyst, backend, python, excel, _ = two_openings
    before = full_state(analyst), full_state(backend)
    url, data = requests_for(python, excel)[which]

    response = htmx_post(client, url, data)

    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={url}"
    assert Skill.objects.count() == 3  # Add didn't create "Kubernetes"
    assert (full_state(analyst), full_state(backend)) == before


@pytest.mark.parametrize("which", [0, 1], ids=["add", "remove"])
def test_deactivated_employee_goes_to_login_and_changes_nothing(
    client, employee, two_openings, which
):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    analyst, backend, python, excel, _ = two_openings
    before = full_state(analyst), full_state(backend)
    url, data = requests_for(python, excel)[which]

    response = htmx_post(client, url, data)

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert Skill.objects.count() == 3
    assert (full_state(analyst), full_state(backend)) == before


@pytest.mark.parametrize("method", ["get", "put", "delete"])
@pytest.mark.parametrize("url", [ADD_URL, REMOVE_URL])
def test_skill_endpoints_are_post_only(employee_client, url, method):
    Skill.objects.create(name="Python")

    response = getattr(employee_client, method)(url)

    assert response.status_code == 405
    assert response["Allow"] == "POST"
    assert Skill.objects.count() == 1


@pytest.fixture
def csrf_client(employee):
    client = Client(enforce_csrf_checks=True)
    client.force_login(employee)
    return client


@pytest.mark.parametrize("which", [0, 1], ids=["add", "remove"])
def test_skill_endpoints_require_csrf_token(csrf_client, two_openings, which):
    analyst, _, python, excel, _ = two_openings
    url, data = requests_for(python, excel)[which]

    # Without a token: refused, nothing created.
    assert htmx_post(csrf_client, url, data).status_code == 403
    assert Skill.objects.count() == 3

    # With the token HTMX sends (from base.html's hx-headers): accepted.
    page = csrf_client.get(f"/openings/{analyst.pk}/edit/").content.decode()
    token = re.search(r'"X-CSRFToken": "([^"]+)"', page).group(1)
    response = csrf_client.post(
        url, data, HTTP_HX_REQUEST="true", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200


# --- Add Skill validation ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("", "This field is required."),
        ("   ", "This field is required."),
        ("x" * 101, "Ensure this value has at most 100 characters"),
    ],
    ids=["blank", "spaces", "too-long"],
)
def test_invalid_new_skill_name_shows_error_and_keeps_pending(
    employee_client, name, error
):
    sql = Skill.objects.create(name="SQL")

    page = htmx_post(
        employee_client, ADD_URL, {"new_skill_name": name, "skills": [sql.pk]}
    ).content.decode()

    assert error in page
    assert Skill.objects.count() == 1
    assert submitted_skill_ids(page) == {sql.pk}


def test_new_skill_name_of_exactly_100_characters_is_accepted(employee_client):
    page = htmx_post(
        employee_client, ADD_URL, {"new_skill_name": "x" * 100}
    ).content.decode()

    skill = Skill.objects.get()
    assert skill.name == "x" * 100
    assert submitted_skill_ids(page) == {skill.pk}


# --- Remove Skill -----------------------------------------------------------


def test_remove_section_hidden_when_form_has_no_skills(employee_client):
    Skill.objects.create(name="Python")  # exists, but isn't on these forms
    empty = JobOpening.objects.create(title="Intern", department="IT")

    for url in ("/openings/new/", f"/openings/{empty.pk}/edit/"):
        page = employee_client.get(url).content.decode()
        assert "No skills yet." in page
        assert "Remove a skill from this opening" not in page
        assert 'id="remove-skill"' not in page


def test_removing_the_last_pending_skill_saves_nothing(employee_client, two_openings):
    analyst, backend, python, *_ = two_openings
    before = full_state(analyst), full_state(backend)

    page = htmx_post(
        employee_client, REMOVE_URL, {"remove_skill": python.pk, "skills": [python.pk]}
    ).content.decode()

    assert assigned_skill_names(page) == set()
    assert submitted_skill_ids(page) == set()
    assert "No skills yet." in page
    assert "Remove a skill from this opening" not in page
    assert Skill.objects.filter(pk=python.pk).exists()
    assert (full_state(analyst), full_state(backend)) == before


# --- Saving -----------------------------------------------------------------


def test_invalid_edit_form_keeps_pending_skills_and_saves_nothing(
    employee_client, two_openings
):
    analyst, backend, python, excel, sql = two_openings
    before = full_state(analyst), full_state(backend)

    # Pending: Python removed, SQL added; but the title is blank, so it's invalid.
    response = employee_client.post(
        f"/openings/{analyst.pk}/edit/",
        {"title": "", "department": "Finance", "skills": [excel.pk, sql.pk]},
    )

    assert response.status_code == 200
    page = response.content.decode()
    assert assigned_skill_names(page) == {"Excel", "SQL"}
    assert submitted_skill_ids(page) == {excel.pk, sql.pk}
    assert python.pk not in submitted_skill_ids(page)  # the pending removal is kept
    assert (full_state(analyst), full_state(backend)) == before


def test_new_opening_gets_skills_only_when_saved(employee_client, two_openings):
    analyst, backend, python, *_ = two_openings
    before = full_state(analyst), full_state(backend)

    # Adding skills on the Create page creates no opening and assigns nothing.
    page = htmx_post(
        employee_client, ADD_URL, {"new_skill_name": "Go", "skills": [python.pk]}
    ).content.decode()
    go = Skill.objects.get(name="Go")
    assert submitted_skill_ids(page) == {python.pk, go.pk}
    assert JobOpening.objects.count() == 2
    assert not go.openings.exists()

    # An invalid Create submission saves no opening either.
    data = {"title": "", "department": "IT", "skills": [python.pk, go.pk]}
    response = employee_client.post("/openings/new/", data)
    assert response.status_code == 200
    assert assigned_skill_names(response.content.decode()) == {"Python", "Go"}
    assert JobOpening.objects.count() == 2

    # A successful Save assigns exactly the pending skills to the new opening.
    data["title"] = "Platform Engineer"
    response = employee_client.post("/openings/new/", data)
    assert response.status_code == 302
    created = JobOpening.objects.get(title="Platform Engineer")
    assert set(created.skills.all()) == {python, go}

    # Other openings, including #2 which shares Python, are unaffected.
    assert (full_state(analyst), full_state(backend)) == before


def test_saving_one_opening_with_added_skill_leaves_others_alone(
    employee_client, two_openings
):
    analyst, backend, python, excel, sql = two_openings
    backend_before = full_state(backend)

    # Opening #1 adds SQL (which #2 also uses) and saves.
    response = employee_client.post(
        f"/openings/{analyst.pk}/edit/",
        {
            "title": "Data Analyst",
            "department": "Finance",
            "skills": [python.pk, excel.pk, sql.pk],
        },
    )

    assert response.status_code == 302
    assert set(JobOpening.objects.get(pk=analyst.pk).skills.all()) == {
        python,
        excel,
        sql,
    }
    assert full_state(backend) == backend_before
    assert Skill.objects.count() == 3
