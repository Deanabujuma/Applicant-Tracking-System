import pytest

from openings.models import JobOpening, Skill

from .test_opening_specific_skills import assigned_skill_names, submitted_skill_ids


@pytest.fixture
def employee_client(client, django_user_model):
    """A client logged in as an ordinary active hiring employee."""
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


@pytest.mark.django_db
def test_removing_shared_skill_from_one_opening_leaves_skill_and_other_openings(
    employee_client,
):
    """Unlinking a skill from one opening never deletes it or touches other openings."""
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")
    opening_a = JobOpening.objects.create(title="Data Analyst", department="Finance")
    opening_b = JobOpening.objects.create(title="Data Engineer", department="IT")
    opening_a.skills.set([python, sql])
    opening_b.skills.set([python, sql])

    response = employee_client.post(
        f"/openings/{opening_a.pk}/edit/",
        {
            "title": "Data Analyst",
            "department": "Finance",
            "description": "",
            "location": "",
            "skills": [sql.pk],
        },
    )

    assert response.status_code == 302
    # Only opening A's link to Python is removed.
    assert set(opening_a.skills.all()) == {sql}
    # The shared Skill record still exists...
    assert Skill.objects.filter(pk=python.pk).exists()
    assert Skill.objects.count() == 2
    # ...and opening B keeps both of its skills.
    assert set(opening_b.skills.all()) == {python, sql}
    assert set(python.openings.all()) == {opening_b}


@pytest.mark.django_db
def test_add_skill_inline_returns_skills_fragment_and_leaves_opening_alone(
    employee_client,
):
    """Adding a skill via HTMX saves only the skill and keeps the form's selections."""
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    opening.skills.set([sql])
    saved_updated_at = opening.updated_at

    # The unsaved form currently has Python ticked (and SQL unticked).
    response = employee_client.post(
        "/openings/skills/new/",
        {"new_skill_name": "  Kubernetes  ", "skills": [python.pk]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200

    # The skill is saved with surrounding spaces removed and capitalization kept.
    kubernetes = Skill.objects.get(name__iexact="kubernetes")
    assert kubernetes.name == "Kubernetes"

    # The response is a fragment, not a full page.
    page = response.content.decode()
    assert "<html" not in page.lower()
    assert "<body" not in page.lower()

    # New skill and the previous pending selection are kept; the unselected one
    # isn't added. (Updated for opening-specific skills, 2026-11-01: the form now
    # submits hidden inputs and lists assigned skills, instead of ticked checkboxes.)
    assert submitted_skill_ids(page) == {kubernetes.pk, python.pk}
    assert assigned_skill_names(page) == {"Kubernetes", "Python"}

    # No JobOpening was created or updated.
    assert JobOpening.objects.count() == 1
    opening.refresh_from_db()
    assert opening.updated_at == saved_updated_at
    assert set(opening.skills.all()) == {sql}


@pytest.mark.django_db
def test_add_skill_inline_reuses_case_only_duplicate_and_keeps_selection(
    employee_client,
):
    """A name differing only in case reuses the existing skill; selections are kept.

    Updated for opening-specific skills (2026-11-01). It was
    test_add_skill_inline_rejects_case_only_duplicate_and_keeps_selection, which
    expected a "duplicate" error. That behavior was intentionally replaced by reuse.
    """
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")

    response = employee_client.post(
        "/openings/skills/new/",
        {"new_skill_name": "python", "skills": [sql.pk]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200

    # No duplicate Skill is created.
    assert Skill.objects.count() == 2
    assert Skill.objects.filter(name__iexact="python").count() == 1

    # The response is a fragment, not a full page.
    page = response.content.decode()
    assert "<html" not in page.lower()
    assert "<body" not in page.lower()

    # No error: the existing record is reused instead of rejected.
    assert "A skill with this name already exists." not in page

    # The previous selection is kept, the existing Python is added, nothing else.
    assert submitted_skill_ids(page) == {sql.pk, python.pk}
    assert assigned_skill_names(page) == {"SQL", "Python"}
