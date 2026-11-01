"""Phase 4: closing, reopening, and deleting job openings."""

import re

import pytest
from django.contrib.messages import get_messages

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


def details(opening):
    """Everything about an opening except status and updated_at, read fresh."""
    opening = JobOpening.objects.get(pk=opening.pk)
    return {
        "title": opening.title,
        "department": opening.department,
        "description": opening.description,
        "location": opening.location,
        "created_at": opening.created_at,
        "skills": set(opening.skills.all()),
    }


def fresh(opening):
    return JobOpening.objects.get(pk=opening.pk)


def test_close_and_reopen_are_one_way_and_change_only_status(employee_client):
    """Close only closes, reopen only reopens; repeats don't flip state or details."""
    opening = JobOpening.objects.create(
        title="Data Analyst",
        department="Finance",
        location="Amarillo",
        description="Builds dashboards.",
    )
    opening.skills.set(
        [Skill.objects.create(name="Python"), Skill.objects.create(name="SQL")]
    )
    original = details(opening)
    close_url = f"/openings/{opening.pk}/close/"
    reopen_url = f"/openings/{opening.pk}/reopen/"

    # Open -> Closed
    response = employee_client.post(close_url)
    assert response.status_code == 302
    assert fresh(opening).status == OpeningStatus.CLOSED
    assert details(opening) == original
    closed_at = fresh(opening).updated_at

    # Repeated close -> still Closed, nothing saved, informational message
    response = employee_client.post(close_url)
    assert response.status_code == 302
    assert fresh(opening).status == OpeningStatus.CLOSED
    assert fresh(opening).updated_at == closed_at
    assert details(opening) == original
    # (the first close's message is still queued because redirects aren't followed)
    latest = list(get_messages(response.wsgi_request))[-1]
    assert "already closed" in latest.message

    # Closed -> Open
    response = employee_client.post(reopen_url)
    assert response.status_code == 302
    assert fresh(opening).status == OpeningStatus.OPEN
    assert details(opening) == original


# Action -> (status the opening starts in, phrases its confirmation must show)
CONFIRMATIONS = {
    "close": (OpeningStatus.OPEN, ["stop accepting new applications"]),
    "reopen": (OpeningStatus.CLOSED, ["accept new applications again"]),
    "delete": (
        OpeningStatus.OPEN,
        ["permanently delete", "cannot be undone", "close it instead"],
    ),
}


def snapshot(opening):
    """The whole stored state of an opening, or None if it no longer exists."""
    opening = JobOpening.objects.filter(pk=opening.pk).first()
    if opening is None:
        return None
    return {
        **details(opening),
        "status": opening.status,
        "updated_at": opening.updated_at,
    }


def check_confirmation(page, opening, action):
    """Assertions shared by the HTMX modal and the full-page confirmation."""
    _, phrases = CONFIRMATIONS[action]
    url = f"/openings/{opening.pk}/{action}/"

    # Identifies the opening and shows the action-specific warning.
    assert f"#{opening.pk}" in page
    for phrase in phrases:
        assert phrase in page

    # Exactly one form POSTs to this action's URL, and it carries a CSRF token.
    post_forms = re.findall(
        rf'<form\b[^>]*method="post"[^>]*action="{url}"[^>]*>.*?</form>',
        page,
        re.DOTALL,
    )
    assert len(post_forms) == 1
    assert 'name="csrfmiddlewaretoken"' in post_forms[0]

    # Cancel only closes the dialog in the browser: no URL, no HTMX, no POST.
    cancel_forms = re.findall(
        r'<form\b[^>]*method="dialog"[^>]*>(.*?)</form>', page, re.DOTALL
    )
    assert len(cancel_forms) == 1
    assert "Cancel" in cancel_forms[0]
    assert "hx-" not in cancel_forms[0]
    assert "href=" not in cancel_forms[0]


@pytest.mark.parametrize("action", CONFIRMATIONS)
def test_confirmation_modal_shows_warning_and_changes_nothing(employee_client, action):
    """Loading any confirmation is harmless; it offers a POST Confirm and a safe Cancel."""
    start_status, _ = CONFIRMATIONS[action]
    opening = JobOpening.objects.create(
        title="Data Analyst", department="Finance", status=start_status
    )
    opening.skills.add(Skill.objects.create(name="Python"))
    before = snapshot(opening)
    url = f"/openings/{opening.pk}/{action}/"

    # HTMX GET -> a modal fragment, not a full page.
    response = employee_client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    fragment = response.content.decode()
    assert "<html" not in fragment.lower()
    assert "<body" not in fragment.lower()
    assert re.search(r'<dialog\b[^>]*class="[^"]*\bmodal\b', fragment)
    check_confirmation(fragment, opening, action)

    # Non-HTMX GET -> a complete page with the same confirmation.
    response = employee_client.get(url)
    assert response.status_code == 200
    page = response.content.decode()
    assert "<html" in page.lower()
    check_confirmation(page, opening, action)

    # Loading either version changed nothing.
    assert snapshot(opening) == before


def test_deleting_unused_opening_keeps_shared_skills_and_other_openings(
    employee_client,
):
    """A confirmed delete removes one opening and its skill links, nothing else."""
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")
    opening_a = JobOpening.objects.create(
        title="Data Analyst", department="Finance", location="Amarillo"
    )
    opening_b = JobOpening.objects.create(
        title="Backend Developer",
        department="IT",
        location="Remote",
        description="Builds APIs.",
        status=OpeningStatus.CLOSED,
    )
    opening_a.skills.set([python, sql])
    opening_b.skills.set([python, sql])
    a_pk = opening_a.pk
    b_before = snapshot(opening_b)
    links = JobOpening.skills.through.objects

    # Confirmed POST -> redirect to the Openings list.
    response = employee_client.post(f"/openings/{a_pk}/delete/")
    assert response.status_code == 302
    assert response["Location"] == "/openings/"

    # Opening A and its skill links are gone for good.
    assert not JobOpening.objects.filter(pk=a_pk).exists()
    assert not links.filter(jobopening_id=a_pk).exists()

    # Both shared Skills still exist, unchanged.
    assert set(Skill.objects.values_list("pk", "name")) == {
        (python.pk, "Python"),
        (sql.pk, "SQL"),
    }

    # Opening B is untouched: every field, timestamp, status, and both skills.
    assert snapshot(opening_b) == b_before
    assert b_before["skills"] == {python, sql}
    assert links.filter(jobopening_id=opening_b.pk).count() == 2

    # The list shows a success message naming the deleted opening, once.
    page = employee_client.get("/openings/").content.decode()
    assert f"Deleted opening #{a_pk} Data Analyst." in page
    assert "alert-success" in page
    page = employee_client.get("/openings/").content.decode()
    assert "Deleted opening" not in page
