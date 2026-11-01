"""Opening-specific skill management (second user-requested change, 2026-11-01)."""

import re

import pytest

from openings.models import JobOpening, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee_client(client, django_user_model):
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


def assigned_skill_names(page):
    """Names shown in the form's "Skills for this opening" list."""
    match = re.search(r'<ul id="assigned-skills"[^>]*>(.*?)</ul>', page, re.DOTALL)
    assert match, "no assigned-skills list on the page"
    return set(re.findall(r"<li\b[^>]*>\s*([^<]+?)\s*</li>", match.group(1)))


def submitted_skill_ids(page):
    """Skill IDs the form would submit: its hidden `skills` inputs."""
    return {
        int(value)
        for value in re.findall(
            r'<input type="hidden" name="skills" value="(\d+)"', page
        )
    }


def skill_checkboxes(page):
    return re.findall(r'<input type="checkbox" name="skills"', page)


def test_form_shows_only_the_openings_own_skills(employee_client):
    python, excel, java, sql = (
        Skill.objects.create(name=name) for name in ("Python", "Excel", "Java", "SQL")
    )
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    analyst.skills.set([python, excel])
    backend = JobOpening.objects.create(title="Backend Developer", department="IT")
    backend.skills.set([java, sql])

    # Opening #1's edit page: only Python and Excel.
    page = employee_client.get(f"/openings/{analyst.pk}/edit/").content.decode()
    assert assigned_skill_names(page) == {"Python", "Excel"}
    assert submitted_skill_ids(page) == {python.pk, excel.pk}
    assert skill_checkboxes(page) == []

    # Opening #2's edit page: only Java and SQL.
    page = employee_client.get(f"/openings/{backend.pk}/edit/").content.decode()
    assert assigned_skill_names(page) == {"Java", "SQL"}
    assert submitted_skill_ids(page) == {java.pk, sql.pk}
    assert skill_checkboxes(page) == []

    # A new opening starts with no assigned skills, despite four existing.
    page = employee_client.get("/openings/new/").content.decode()
    assert assigned_skill_names(page) == set()
    assert submitted_skill_ids(page) == set()
    assert skill_checkboxes(page) == []


def add_skill(client, name, pending_ids):
    """The HTMX Add Skill request, as the form's button sends it."""
    return client.post(
        "/openings/skills/new/",
        {"new_skill_name": name, "skills": pending_ids},
        HTTP_HX_REQUEST="true",
    )


def saved_state(opening):
    opening = JobOpening.objects.get(pk=opening.pk)
    return opening.updated_at, set(opening.skills.all())


def test_add_skill_reuses_existing_skill_case_insensitively(employee_client):
    """Adding an existing name attaches that shared record to the pending form only."""
    python, excel, java = (
        Skill.objects.create(name=name) for name in ("Python", "Excel", "Java")
    )
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    analyst.skills.set([excel])
    backend = JobOpening.objects.create(title="Backend Developer", department="IT")
    backend.skills.set([python])
    before = {o.pk: saved_state(o) for o in (analyst, backend)}

    # Opening #1's unsaved form holds Excel, plus a forged and a junk ID.
    response = add_skill(employee_client, "python", [excel.pk, 99999, "abc"])
    assert response.status_code == 200
    page = response.content.decode()

    # The exact existing "Python" record is reused; no duplicate is created.
    assert Skill.objects.count() == 3
    assert submitted_skill_ids(page) == {excel.pk, python.pk}
    assert assigned_skill_names(page) == {"Excel", "Python"}
    assert "already" not in page

    # Still an HTMX fragment that only posts the skills inputs, so the rest of
    # the unsaved opening form is left alone in the browser.
    assert "<html" not in page.lower()
    assert 'name="title"' not in page
    assert 'hx-params="new_skill_name,skills"' in page

    # Existing names are suggested, but suggestions are not assignments.
    datalist = re.search(
        r'<datalist id="skill-suggestions">(.*?)</datalist>', page, re.DOTALL
    )
    assert datalist, "no skill-suggestions datalist"
    assert set(re.findall(r'<option value="([^"]+)"', datalist.group(1))) == {
        "Python",
        "Excel",
        "Java",
    }
    assert 'list="skill-suggestions"' in page
    assert java.name not in assigned_skill_names(page)

    # Adding a name already in the pending form, in any capitalization: message,
    # pending skills kept, still no new Skill.
    response = add_skill(employee_client, "PYTHON", [excel.pk, python.pk])
    page = response.content.decode()
    assert "Python is already on this opening." in page
    assert submitted_skill_ids(page) == {excel.pk, python.pk}
    assert Skill.objects.count() == 3

    # The HTMX action saved nothing: no opening or skill link changed.
    assert JobOpening.objects.count() == 2
    assert {o.pk: saved_state(o) for o in (analyst, backend)} == before

    # A forged skill ID is not accepted when the opening is saved either.
    response = employee_client.post(
        f"/openings/{analyst.pk}/edit/",
        {"title": "Data Analyst", "department": "Finance", "skills": [99999]},
    )
    assert response.status_code == 200  # form re-shown with an error, not saved
    assert saved_state(analyst) == before[analyst.pk]


def remove_options(page):
    """(id, label) pairs offered by the "Remove a skill" dropdown."""
    match = re.search(
        r'<select id="remove-skill" name="remove_skill"[^>]*>(.*?)</select>',
        page,
        re.DOTALL,
    )
    assert match, "no remove-skill dropdown"
    return {
        (int(pk), label.strip())
        for pk, label in re.findall(
            r'<option value="(\d+)"[^>]*>([^<]*)</option>', match.group(1)
        )
    }


def remove_skill(client, remove_id, pending_ids):
    """The HTMX Remove request, as the form's Remove button sends it."""
    return client.post(
        "/openings/skills/remove/",
        {"remove_skill": remove_id, "skills": pending_ids},
        HTTP_HX_REQUEST="true",
    )


def full_state(opening):
    """Every stored field of an opening, plus its skills."""
    opening = JobOpening.objects.get(pk=opening.pk)
    return {
        "title": opening.title,
        "department": opening.department,
        "description": opening.description,
        "location": opening.location,
        "status": opening.status,
        "created_at": opening.created_at,
        "updated_at": opening.updated_at,
        "skills": set(opening.skills.all()),
    }


def test_remove_skill_changes_only_this_openings_pending_form(employee_client):
    """Remove drops a skill from one form; only Save unlinks it, from one opening."""
    python, excel, sql = (
        Skill.objects.create(name=name) for name in ("Python", "Excel", "SQL")
    )
    analyst = JobOpening.objects.create(
        title="Data Analyst", department="Finance", location="Amarillo"
    )
    analyst.skills.set([python, excel])
    backend = JobOpening.objects.create(
        title="Backend Developer", department="IT", description="Builds APIs."
    )
    backend.skills.set([python, sql])
    analyst_before, backend_before = full_state(analyst), full_state(backend)

    # The Remove control sits below Add Skill and offers only this opening's skills.
    page = employee_client.get(f"/openings/{analyst.pk}/edit/").content.decode()
    assert remove_options(page) == {(python.pk, "Python"), (excel.pk, "Excel")}
    assert "Remove a skill from this opening" in page
    assert page.index("Add skill</button>") < page.index(
        "Remove a skill from this opening"
    )
    assert 'hx-post="/openings/skills/remove/"' in page
    assert 'hx-params="skills,remove_skill"' in page  # never the other form inputs

    # Removing Python changes only the pending form returned in the fragment.
    response = remove_skill(employee_client, python.pk, [python.pk, excel.pk])
    assert response.status_code == 200
    page = response.content.decode()
    assert "<html" not in page.lower()
    assert 'name="title"' not in page  # the unsaved title etc. are left alone
    assert assigned_skill_names(page) == {"Excel"}
    assert submitted_skill_ids(page) == {excel.pk}
    assert remove_options(page) == {(excel.pk, "Excel")}

    # Bad removal requests can't drop anything else from the pending form:
    # a nonexistent ID, junk, or a skill that isn't in this form (SQL is #2's).
    for bad in (99999, "abc", sql.pk):
        response = remove_skill(employee_client, bad, [python.pk, excel.pk, 88888])
        page = response.content.decode()
        assert submitted_skill_ids(page) == {python.pk, excel.pk}

    # Before Save, nothing in the database has changed.
    assert full_state(analyst) == analyst_before
    assert full_state(backend) == backend_before

    # Leaving without saving (Cancel goes back to the opening) changes nothing.
    page = employee_client.get(f"/openings/{analyst.pk}/edit/").content.decode()
    assert f'href="/openings/{analyst.pk}/" class="btn btn-ghost">Cancel' in page
    assert assigned_skill_names(page) == {"Python", "Excel"}
    assert full_state(analyst) == analyst_before

    # Saving the form with Python removed unlinks it from Opening #1 only.
    response = employee_client.post(
        f"/openings/{analyst.pk}/edit/",
        {
            "title": "Data Analyst",
            "department": "Finance",
            "location": "Amarillo",
            "description": "",
            "skills": [excel.pk],
        },
    )
    assert response.status_code == 302
    assert set(JobOpening.objects.get(pk=analyst.pk).skills.all()) == {excel}
    assert full_state(backend) == backend_before
    assert Skill.objects.filter(pk=python.pk, name="Python").exists()
    assert Skill.objects.count() == 3
