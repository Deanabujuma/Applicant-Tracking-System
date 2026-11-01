"""Phase 4 regression tests: access, errors, messages, buttons, and request safety."""

import re

import pytest
from django.test import Client

from openings.models import JobOpening, OpeningStatus, Skill

from .test_close_reopen import snapshot

pytestmark = pytest.mark.django_db

ACTIONS = ("close", "reopen", "delete")
# The status each action is normally used from.
START_STATUS = {
    "close": OpeningStatus.OPEN,
    "reopen": OpeningStatus.CLOSED,
    "delete": OpeningStatus.OPEN,
}


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


def make_opening(status=OpeningStatus.OPEN):
    opening = JobOpening.objects.create(
        title="Data Analyst",
        department="Finance",
        location="Amarillo",
        description="Builds dashboards.",
        status=status,
    )
    opening.skills.add(Skill.objects.get_or_create(name="Python")[0])
    return opening


def url_for(opening_pk, action):
    return f"/openings/{opening_pk}/{action}/"


def alerts(page):
    """(alert class, text) for every message alert on a rendered page."""
    return re.findall(r'<div role="alert" class="alert (alert-\w+)">(.*?)</div>', page)


# --- Login and deactivated accounts ----------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("action", ACTIONS)
def test_anonymous_requests_redirect_to_login_and_change_nothing(
    client, action, method
):
    opening = make_opening(START_STATUS[action])
    before = snapshot(opening)
    url = url_for(opening.pk, action)

    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={url}"
    assert snapshot(opening) == before


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("action", ACTIONS)
def test_deactivated_employee_is_sent_to_login_and_changes_nothing(
    client, employee, action, method
):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    opening = make_opening(START_STATUS[action])
    before = snapshot(opening)

    response = getattr(client, method)(url_for(opening.pk, action))

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert snapshot(opening) == before


# --- Nonexistent openings ---------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("action", ACTIONS)
def test_nonexistent_opening_returns_404(employee_client, action, method):
    other = make_opening(START_STATUS[action])
    before = snapshot(other)

    response = getattr(employee_client, method)(url_for(other.pk + 999, action))

    assert response.status_code == 404
    assert snapshot(other) == before


def test_repeated_delete_is_404_and_harmless(employee_client):
    opening = make_opening()
    other = make_opening()
    other_before = snapshot(other)
    url = url_for(opening.pk, "delete")

    assert employee_client.post(url).status_code == 302
    assert employee_client.post(url).status_code == 404
    assert snapshot(other) == other_before  # still linked to the shared skill
    assert Skill.objects.count() == 1


# --- Messages ---------------------------------------------------------------


CLOSED_TEXT = (
    "Closed opening #{pk} Data Analyst. It no longer accepts new applications."
)
REOPENED_TEXT = (
    "Reopened opening #{pk} Data Analyst. It accepts new applications again."
)


@pytest.mark.parametrize(
    ("action", "start", "expected"),
    [
        ("close", OpeningStatus.OPEN, ("alert-success", CLOSED_TEXT)),
        ("reopen", OpeningStatus.CLOSED, ("alert-success", REOPENED_TEXT)),
        (
            "close",
            OpeningStatus.CLOSED,
            ("alert-info", "Opening #{pk} Data Analyst is already closed."),
        ),
        (
            "reopen",
            OpeningStatus.OPEN,
            ("alert-info", "Opening #{pk} Data Analyst is already open."),
        ),
    ],
)
def test_status_change_shows_one_time_message_on_detail_page(
    employee_client, action, start, expected
):
    opening = make_opening(start)

    response = employee_client.post(url_for(opening.pk, action), follow=True)

    assert response.redirect_chain == [(f"/openings/{opening.pk}/", 302)]
    kind, text = expected
    assert alerts(response.content.decode()) == [(kind, text.format(pk=opening.pk))]
    again = employee_client.get(f"/openings/{opening.pk}/").content.decode()
    assert alerts(again) == []


def test_delete_message_is_success_alert_shown_once(employee_client):
    opening = make_opening()
    pk = opening.pk

    response = employee_client.post(url_for(pk, "delete"), follow=True)

    assert response.redirect_chain == [("/openings/", 302)]
    page = response.content.decode()
    assert alerts(page) == [("alert-success", f"Deleted opening #{pk} Data Analyst.")]
    assert alerts(employee_client.get("/openings/").content.decode()) == []


# --- Detail page buttons ----------------------------------------------------


def action_link(page, action, pk):
    """The detail page's HTMX link for an action, or None."""
    url = url_for(pk, action)
    match = re.search(
        rf'<a href="{url}" hx-get="{url}" hx-target="#modal"[^>]*>([^<]*)</a>', page
    )
    return match.group(1) if match else None


@pytest.mark.parametrize(
    ("status", "shown", "hidden"),
    [
        (OpeningStatus.OPEN, ("close", "Close opening"), "reopen"),
        (OpeningStatus.CLOSED, ("reopen", "Reopen opening"), "close"),
    ],
)
def test_detail_page_shows_matching_status_button_and_delete(
    employee_client, status, shown, hidden
):
    opening = make_opening(status)

    page = employee_client.get(f"/openings/{opening.pk}/").content.decode()

    action, label = shown
    assert action_link(page, action, opening.pk) == label
    assert action_link(page, hidden, opening.pk) is None
    assert url_for(opening.pk, hidden) not in page
    assert action_link(page, "delete", opening.pk) == "Delete"
    assert '<div id="modal"></div>' in page


# --- Status can't change through the edit form ------------------------------


@pytest.mark.parametrize(
    ("start", "posted"),
    [(OpeningStatus.OPEN, "closed"), (OpeningStatus.CLOSED, "open")],
)
def test_edit_form_ignores_posted_status(employee_client, start, posted):
    opening = make_opening(start)

    response = employee_client.post(
        f"/openings/{opening.pk}/edit/",
        {
            "title": "Senior Data Analyst",
            "department": "Finance",
            "location": "Amarillo",
            "description": "Builds dashboards.",
            "status": posted,
        },
    )

    assert response.status_code == 302
    opening.refresh_from_db()
    assert opening.title == "Senior Data Analyst"  # the edit itself worked
    assert opening.status == start


# --- Full-page fallback and read-only GETs ----------------------------------


@pytest.mark.parametrize("action", ACTIONS)
def test_non_htmx_confirmation_is_full_site_page(employee_client, action):
    opening = make_opening(START_STATUS[action])

    page = employee_client.get(url_for(opening.pk, action)).content.decode()

    assert "<title>Confirm · Opening #" in page
    assert 'href="/openings/"' in page  # site navigation from base.html
    assert f'<a href="/openings/{opening.pk}/" class="link">Back to opening' in page
    assert re.search(r"<dialog\b[^>]*\bopen\b", page)


@pytest.mark.parametrize("status", OpeningStatus.values)
@pytest.mark.parametrize("action", ACTIONS)
def test_get_never_changes_data_in_either_status(employee_client, action, status):
    """Even 'wrong-state' GETs (e.g. reopen an Open opening) only show a dialog."""
    opening = make_opening(status)
    before = snapshot(opening)
    url = url_for(opening.pk, action)

    for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
        for _ in range(2):
            assert employee_client.get(url, **headers).status_code == 200

    assert snapshot(opening) == before
    assert Skill.objects.count() == 1


# --- Unsupported methods ----------------------------------------------------


@pytest.mark.parametrize("method", ["put", "patch", "delete", "head", "options"])
@pytest.mark.parametrize("action", ACTIONS)
def test_unsupported_methods_return_405_and_change_nothing(
    employee_client, action, method
):
    opening = make_opening(START_STATUS[action])
    before = snapshot(opening)

    response = getattr(employee_client, method)(url_for(opening.pk, action))

    assert response.status_code == 405
    assert sorted(response["Allow"].split(", ")) == ["GET", "POST"]
    assert snapshot(opening) == before


# --- CSRF -------------------------------------------------------------------


@pytest.fixture
def csrf_client(employee):
    client = Client(enforce_csrf_checks=True)
    client.force_login(employee)
    return client


@pytest.mark.parametrize("action", ACTIONS)
def test_post_without_csrf_token_is_rejected(csrf_client, action):
    opening = make_opening(START_STATUS[action])
    before = snapshot(opening)

    response = csrf_client.post(url_for(opening.pk, action))

    assert response.status_code == 403
    assert snapshot(opening) == before


@pytest.mark.parametrize("action", ACTIONS)
def test_post_with_confirmation_forms_csrf_token_succeeds(csrf_client, action):
    opening = make_opening(START_STATUS[action])
    url = url_for(opening.pk, action)
    page = csrf_client.get(url, HTTP_HX_REQUEST="true").content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)

    response = csrf_client.post(url, {"csrfmiddlewaretoken": token})

    assert response.status_code == 302
    if action == "delete":
        assert not JobOpening.objects.filter(pk=opening.pk).exists()
    else:
        assert fresh_status(opening) != START_STATUS[action]


def fresh_status(opening):
    return JobOpening.objects.get(pk=opening.pk).status
