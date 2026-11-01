"""Phase 3 (user-requested change): Manage Skills and safe skill deletion."""

import re

import pytest
from django.contrib import messages
from django.contrib.messages import get_messages
from django.utils.html import escape

from openings.models import JobOpening, OpeningStatus, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee_client(client, django_user_model):
    """A client logged in as an ordinary active hiring employee."""
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


def form_tags(page):
    return re.findall(r"<form\b[^>]*>", page)


def test_confirmation_page_shows_skill_and_count_without_deleting(employee_client):
    """Opening the delete confirmation shows what would be lost and changes nothing."""
    python = Skill.objects.create(name="Python")
    open_opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    closed_opening = JobOpening.objects.create(
        title="Data Engineer", department="IT", status=OpeningStatus.CLOSED
    )
    open_opening.skills.add(python)
    closed_opening.skills.add(python)
    url = f"/openings/skills/{python.pk}/delete/"

    response = employee_client.get(url)

    assert response.status_code == 200
    page = response.content.decode()
    assert "Python" in page
    assert "2 openings" in page  # Open and Closed openings both count

    # The page offers a confirmation form that POSTs back to this URL.
    confirm_forms = [
        tag
        for tag in form_tags(page)
        if 'method="post"' in tag and f'action="{url}"' in tag
    ]
    assert len(confirm_forms) == 1

    # Loading the page deleted nothing and unlinked nothing.
    assert Skill.objects.filter(pk=python.pk).exists()
    assert set(python.openings.all()) == {open_opening, closed_opening}


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


def test_confirmed_delete_removes_skill_and_its_links_but_not_openings(
    employee_client,
):
    """A confirmed POST deletes only the skill and its links; openings are untouched."""
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

    response = employee_client.post(f"/openings/skills/{python.pk}/delete/")

    assert response.status_code == 302

    # Python is permanently deleted, and with it every opening link to it.
    assert not Skill.objects.filter(pk=python.pk).exists()
    assert not JobOpening.skills.through.objects.filter(skill_id=python.pk).exists()

    # SQL still exists, and both openings still exist, keep SQL, and are unchanged.
    assert Skill.objects.filter(pk=sql.pk).exists()
    assert JobOpening.objects.count() == 2
    for opening in (analyst, engineer):
        assert set(opening.skills.all()) == {sql}
        assert snapshot(opening) == before[opening.pk]

    # The employee is sent back to Manage Skills...
    assert response.url == "/openings/skills/"

    # ...with a one-time success message naming the skill and the openings affected.
    [message] = list(get_messages(response.wsgi_request))
    assert message.level == messages.SUCCESS
    assert "Python" in message.message
    assert "2 openings" in message.message

    # The message is shown on the next page, then not again.
    first = employee_client.get("/openings/skills/").content.decode()
    second = employee_client.get("/openings/skills/").content.decode()
    # (rendered with normal template escaping, so quotes appear as &quot;)
    assert escape(message.message) in first
    assert escape(message.message) not in second


def row_for(page, text):
    """The table row (<tr>...</tr>) on the page containing ``text``; fails if none."""
    rows = [r for r in re.findall(r"<tr\b.*?</tr>", page, re.DOTALL) if text in r]
    assert len(rows) == 1, f"expected one table row containing {text!r}"
    return rows[0]


def test_manage_skills_lists_each_skill_with_count_and_delete_link(employee_client):
    """Every skill is listed A-Z ignoring case, with its opening count and Delete link."""
    python = Skill.objects.create(name="python")
    django_skill = Skill.objects.create(name="Django")
    agile = Skill.objects.create(name="agile")
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    engineer = JobOpening.objects.create(
        title="Data Engineer", department="IT", status=OpeningStatus.CLOSED
    )
    analyst.skills.set([python, django_skill])
    engineer.skills.set([python])  # Closed openings count too

    response = employee_client.get("/openings/skills/")

    assert response.status_code == 200
    page = response.content.decode()

    # All three skills appear, sorted A-Z ignoring capitalization
    # (case-sensitive sorting would put "Django" before "agile").
    assert list(response.context["skills"]) == [agile, django_skill, python]
    positions = [
        page.index(f">{skill.name}<") for skill in (agile, django_skill, python)
    ]
    assert positions == sorted(positions)

    # Each skill's row shows its opening count and links to its own confirmation page.
    expected_counts = {
        agile: "0 openings",
        django_skill: "1 opening",
        python: "2 openings",
    }
    for skill, count_text in expected_counts.items():
        row = row_for(page, f">{skill.name}<")
        assert count_text in row
        assert f'href="/openings/skills/{skill.pk}/delete/"' in row


# --- Regression tests (not test-first) -------------------------------------


def make_linked_skill():
    """A skill used by one opening, plus that opening."""
    skill = Skill.objects.create(name="Python")
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    opening.skills.add(skill)
    return skill, opening


def test_cancel_returns_to_manage_skills_and_changes_nothing(employee_client):
    skill, opening = make_linked_skill()
    page = employee_client.get(f"/openings/skills/{skill.pk}/delete/").content.decode()

    cancel = re.search(r'<a href="([^"]+)"[^>]*>Cancel</a>', page)
    assert cancel and cancel.group(1) == "/openings/skills/"

    assert employee_client.get(cancel.group(1)).status_code == 200
    assert Skill.objects.filter(pk=skill.pk).exists()
    assert set(opening.skills.all()) == {skill}


@pytest.mark.parametrize("path", ["/openings/skills/", "/openings/skills/{pk}/delete/"])
def test_manage_skills_pages_require_login(client, path):
    skill, _ = make_linked_skill()
    url = path.format(pk=skill.pk)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={url}"


def test_anonymous_post_cannot_delete_a_skill(client):
    skill, opening = make_linked_skill()

    response = client.post(f"/openings/skills/{skill.pk}/delete/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert Skill.objects.filter(pk=skill.pk).exists()
    assert set(opening.skills.all()) == {skill}


def test_deactivated_employee_cannot_delete_a_skill(client, django_user_model):
    employee = django_user_model.objects.create_user(
        username="former", password="correct-horse-42"
    )
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    skill, opening = make_linked_skill()

    response = client.post(f"/openings/skills/{skill.pk}/delete/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert Skill.objects.filter(pk=skill.pk).exists()
    assert set(opening.skills.all()) == {skill}


@pytest.mark.parametrize("method", ["get", "post"])
def test_nonexistent_skill_returns_404(employee_client, method):
    Skill.objects.create(name="SQL")

    response = getattr(employee_client, method)("/openings/skills/99999/delete/")

    assert response.status_code == 404
    assert Skill.objects.count() == 1


def test_repeated_delete_request_is_404_and_harmless(employee_client):
    skill, _ = make_linked_skill()
    sql = Skill.objects.create(name="SQL")
    url = f"/openings/skills/{skill.pk}/delete/"

    first = employee_client.post(url)
    second = employee_client.post(url)

    assert first.status_code == 302
    assert second.status_code == 404
    assert list(Skill.objects.all()) == [sql]
    assert len(list(get_messages(second.wsgi_request))) == 1  # only the first


def test_success_message_uses_singular_for_one_opening(employee_client):
    skill, _ = make_linked_skill()

    response = employee_client.post(f"/openings/skills/{skill.pk}/delete/")

    [message] = list(get_messages(response.wsgi_request))
    assert message.message == 'Deleted skill "Python" (removed from 1 opening).'


def test_openings_page_links_to_manage_skills_and_back(employee_client):
    openings_page = employee_client.get("/openings/").content.decode()
    skills_page = employee_client.get("/openings/skills/").content.decode()

    assert 'href="/openings/skills/"' in openings_page
    assert 'href="/openings/"' in skills_page


def test_deleted_skill_disappears_from_opening_form(employee_client):
    skill, opening = make_linked_skill()
    employee_client.post(f"/openings/skills/{skill.pk}/delete/")

    page = employee_client.get(f"/openings/{opening.pk}/edit/").content.decode()

    assert f'value="{skill.pk}"' not in page
    assert ">Python<" not in page


def test_stale_opening_form_with_deleted_skill_is_rejected_safely(employee_client):
    skill, opening = make_linked_skill()
    employee_client.post(f"/openings/skills/{skill.pk}/delete/")

    # An edit form opened before the deletion still has the old skill ticked.
    response = employee_client.post(
        f"/openings/{opening.pk}/edit/",
        {"title": "Changed", "department": "Finance", "skills": [skill.pk]},
    )

    assert response.status_code == 200
    assert "skills" in response.context["form"].errors
    opening.refresh_from_db()
    assert opening.title == "Data Analyst"
