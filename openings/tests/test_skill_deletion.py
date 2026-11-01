"""Skill deletion safety, and the retired global Manage Skills page.

History: this file began as the Phase 3 Manage Skills tests (user-requested
change, 2026-11-01). The second 2026-11-01 change withdrew that employee page;
skills are now deleted only by administrators in Django Admin. Tests for the
retired page were replaced by tests that its URLs no longer work. The data
safety tests were kept, now deleting through the model the way Admin does.
"""

import pytest
from django.contrib import admin

from openings.models import JobOpening, OpeningStatus, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )


@pytest.fixture
def employee_client(client, employee):
    """A client logged in as an ordinary active (non-staff) hiring employee."""
    client.force_login(employee)
    return client


def snapshot(opening):
    """Every stored field of an opening, read fresh from the database."""
    opening = JobOpening.objects.get(pk=opening.pk)
    return {
        "title": opening.title,
        "department": opening.department,
        "description": opening.description,
        "location": opening.location,
        "status": opening.status,
        "created_at": opening.created_at,
        "updated_at": opening.updated_at,
    }


def make_linked_skill():
    """A skill used by one opening, plus that opening."""
    skill = Skill.objects.create(name="Python")
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    opening.skills.add(skill)
    return skill, opening


# --- Kept: deleting a Skill (now only via Django Admin) ---------------------


def test_deleting_a_skill_removes_only_it_and_its_links_not_openings():
    """Kept from the original confirmed-delete test, now deleting via the model."""
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")
    analyst = JobOpening.objects.create(
        title="Data Analyst", department="Finance", location="Amarillo"
    )
    engineer = JobOpening.objects.create(
        title="Data Engineer", department="IT", status=OpeningStatus.CLOSED
    )
    analyst.skills.set([python, sql])
    engineer.skills.set([python, sql])
    before = {analyst.pk: snapshot(analyst), engineer.pk: snapshot(engineer)}

    python.delete()

    # Python is permanently deleted, and with it every opening link to it.
    assert not Skill.objects.filter(pk=python.pk).exists()
    assert not JobOpening.skills.through.objects.filter(skill_id=python.pk).exists()

    # SQL still exists, and both openings still exist, keep SQL, and are unchanged.
    assert Skill.objects.filter(pk=sql.pk).exists()
    assert JobOpening.objects.count() == 2
    for opening in (analyst, engineer):
        assert set(opening.skills.all()) == {sql}
        assert snapshot(opening) == before[opening.pk]


def test_deleted_skill_disappears_from_opening_form(employee_client):
    skill, opening = make_linked_skill()
    skill.delete()

    page = employee_client.get(f"/openings/{opening.pk}/edit/").content.decode()

    assert f'value="{skill.pk}"' not in page
    assert ">Python<" not in page


def test_stale_opening_form_with_deleted_skill_is_rejected_safely(employee_client):
    skill, opening = make_linked_skill()
    skill.delete()

    # An edit form opened before the deletion still submits the old skill's ID.
    response = employee_client.post(
        f"/openings/{opening.pk}/edit/",
        {"title": "Changed", "department": "Finance", "skills": [skill.pk]},
    )

    assert response.status_code == 200
    assert "skills" in response.context["form"].errors
    opening.refresh_from_db()
    assert opening.title == "Data Analyst"


# --- Django Admin is the only place to delete skills ------------------------


def test_skill_is_registered_in_django_admin():
    assert admin.site.is_registered(Skill)


@pytest.mark.parametrize(
    "path", ["/admin/openings/skill/", "/admin/openings/skill/{pk}/delete/"]
)
@pytest.mark.parametrize("method", ["get", "post"])
def test_ordinary_employee_cannot_delete_skills_in_admin(
    employee_client, employee, path, method
):
    """Admin needs staff status; ordinary employees are sent to the admin login."""
    assert not employee.is_staff
    skill, opening = make_linked_skill()
    url = path.format(pk=skill.pk)

    response = getattr(employee_client, method)(url, {"post": "yes"})

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")
    assert Skill.objects.filter(pk=skill.pk).exists()
    assert set(opening.skills.all()) == {skill}


# --- Retired: the global Manage Skills page ---------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("path", ["/openings/skills/", "/openings/skills/{pk}/delete/"])
def test_retired_manage_skills_urls_are_gone_and_delete_nothing(
    employee_client, path, method
):
    """Typing an old Manage Skills URL finds nothing and deletes nothing."""
    skill, opening = make_linked_skill()
    sql = Skill.objects.create(name="SQL")

    response = getattr(employee_client, method)(path.format(pk=skill.pk))

    assert response.status_code == 404
    assert set(Skill.objects.all()) == {skill, sql}
    assert set(opening.skills.all()) == {skill}


@pytest.mark.parametrize("path", ["/openings/skills/", "/openings/skills/{pk}/delete/"])
def test_retired_manage_skills_urls_delete_nothing_for_anonymous_users(client, path):
    skill, opening = make_linked_skill()

    response = client.post(path.format(pk=skill.pk))

    # The URL no longer resolves, so it is a 404 before login is even checked.
    assert response.status_code == 404
    assert Skill.objects.filter(pk=skill.pk).exists()
    assert set(opening.skills.all()) == {skill}


def test_openings_pages_no_longer_link_to_manage_skills(employee_client):
    _, opening = make_linked_skill()
    pages = [
        employee_client.get(url).content.decode()
        for url in ("/openings/", f"/openings/{opening.pk}/", "/openings/new/")
    ]

    for page in pages:
        assert 'href="/openings/skills/"' not in page
        assert "Manage skills" not in page
        assert "/delete/" not in page.replace(f"/openings/{opening.pk}/delete/", "")
