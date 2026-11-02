"""Phase 6 regression tests: archive/unarchive access, idempotence, and pages."""

import re

import pytest
from django.test import Client
from django.utils.html import escape

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

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


def candidate_state(candidate):
    return Candidate.objects.filter(pk=candidate.pk).values().get()


def applications_state():
    return list(Application.objects.order_by("pk").values())


def alerts(page):
    """(alert class, text) for every message alert on a rendered page."""
    return re.findall(r'<div role="alert" class="alert (alert-\w+)">(.*?)</div>', page)


def archive_url(candidate):
    return f"/candidates/{candidate.pk}/archive/"


def unarchive_url(candidate):
    return f"/candidates/{candidate.pk}/unarchive/"


@pytest.fixture
def blocked(employee):
    """Jane, with one active application (blocks archiving) and one closed one."""
    jane = make_candidate("Jane")
    for title, stage in (("Data Analyst", Stage.SCREENING), ("Designer", Stage.HIRED)):
        Application.objects.create(
            candidate=jane,
            opening=JobOpening.objects.create(title=title, department="IT"),
            stage=stage,
            stage_changed_by=employee,
        )
    return jane


# --- Access -----------------------------------------------------------------

# (url maker, method, whether the candidate starts archived)
REQUESTS = [
    (archive_url, "get", False),
    (archive_url, "post", False),
    (unarchive_url, "post", True),
]


@pytest.mark.parametrize(("url_for", "method", "archived"), REQUESTS)
def test_anonymous_users_are_sent_to_login(client, url_for, method, archived):
    sam = make_candidate("Sam", archived=archived)
    before = candidate_state(sam)
    url = url_for(sam)

    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={url}"
    assert candidate_state(sam) == before


@pytest.mark.parametrize(("url_for", "method", "archived"), REQUESTS)
def test_deactivated_employees_are_sent_to_login(
    client, employee, url_for, method, archived
):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    sam = make_candidate("Sam", archived=archived)
    before = candidate_state(sam)

    response = getattr(client, method)(url_for(sam))

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert candidate_state(sam) == before


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("archive", "get"),
        ("archive", "post"),
        ("unarchive", "post"),
    ],
)
def test_nonexistent_candidate_is_404(employee_client, path, method):
    sam = make_candidate("Sam")

    response = getattr(employee_client, method)(f"/candidates/{sam.pk + 999}/{path}/")

    assert response.status_code == 404
    assert candidate_state(sam)["is_archived"] is False


@pytest.mark.parametrize(
    ("url_for", "method"),
    [
        (archive_url, "put"),
        (archive_url, "patch"),
        (archive_url, "delete"),
        (unarchive_url, "get"),
        (unarchive_url, "put"),
        (unarchive_url, "delete"),
    ],
)
def test_unsupported_methods_return_405(employee_client, url_for, method):
    sam = make_candidate("Sam", archived=url_for is unarchive_url)
    before = candidate_state(sam)

    response = getattr(employee_client, method)(url_for(sam))

    assert response.status_code == 405
    assert candidate_state(sam) == before


@pytest.fixture
def csrf_client(employee):
    client = Client(enforce_csrf_checks=True)
    client.force_login(employee)
    return client


@pytest.mark.parametrize(
    ("url_for", "archived", "token_page"),
    [
        (archive_url, False, archive_url),  # token from the confirmation
        (unarchive_url, True, lambda c: f"/candidates/{c.pk}/"),  # from detail
    ],
)
def test_archive_and_unarchive_require_csrf(csrf_client, url_for, archived, token_page):
    sam = make_candidate("Sam", archived=archived)
    before = candidate_state(sam)

    assert csrf_client.post(url_for(sam)).status_code == 403
    assert candidate_state(sam) == before

    page = csrf_client.get(token_page(sam)).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    response = csrf_client.post(url_for(sam), {"csrfmiddlewaretoken": token})
    assert response.status_code == 302
    assert candidate_state(sam)["is_archived"] is (not archived)


# --- Messages and idempotence -----------------------------------------------


@pytest.mark.parametrize(
    ("archived", "url_for", "expected"),
    [
        (
            False,
            archive_url,
            (
                "alert-success",
                "Archived Sam Doe. They're hidden from the active candidate list.",
            ),
        ),
        (True, archive_url, ("alert-info", "Sam Doe is already archived.")),
        (
            True,
            unarchive_url,
            ("alert-success", "Unarchived Sam Doe. They're back in the active list."),
        ),
        (False, unarchive_url, ("alert-info", "Sam Doe isn't archived.")),
    ],
    ids=["archive", "archive-again", "unarchive", "unarchive-active"],
)
def test_messages_appear_once(employee_client, archived, url_for, expected):
    sam = make_candidate("Sam", archived=archived)

    response = employee_client.post(url_for(sam), follow=True)

    assert response.redirect_chain == [(f"/candidates/{sam.pk}/", 302)]
    kind, text = expected
    assert alerts(response.content.decode()) == [(kind, escape(text))]
    assert alerts(employee_client.get(f"/candidates/{sam.pk}/").content.decode()) == []


def test_refusal_message_appears_once(employee_client, blocked):
    response = employee_client.post(archive_url(blocked), follow=True)

    [(kind, text)] = alerts(response.content.decode())
    assert kind == "alert-error"
    opening = JobOpening.objects.get(title="Data Analyst")
    assert text == escape(
        "Jane Doe can't be archived while they have active applications: "
        f"#{opening.pk} Data Analyst (Screening). Resolve these first."
    )
    assert (
        alerts(employee_client.get(f"/candidates/{blocked.pk}/").content.decode()) == []
    )


def test_archiving_an_archived_candidate_changes_nothing(employee_client):
    sam = make_candidate("Sam", archived=True)
    before = candidate_state(sam)

    employee_client.post(archive_url(sam))

    assert candidate_state(sam) == before  # including updated_at


def test_unarchiving_an_active_candidate_changes_nothing(employee_client):
    sam = make_candidate("Sam")
    before = candidate_state(sam)

    employee_client.post(unarchive_url(sam))

    assert candidate_state(sam) == before  # including updated_at


def test_blocked_archive_preserves_every_field(employee_client, blocked):
    candidates_before = list(Candidate.objects.order_by("pk").values())
    apps_before = applications_state()

    for _ in range(2):
        employee_client.post(archive_url(blocked))

    assert list(Candidate.objects.order_by("pk").values()) == candidates_before
    assert applications_state() == apps_before


@pytest.mark.parametrize("archived", [False, True])
def test_archive_get_never_modifies_records(employee_client, blocked, archived):
    sam = make_candidate("Sam", archived=archived)
    candidates_before = list(Candidate.objects.order_by("pk").values())
    apps_before = applications_state()

    for candidate in (sam, blocked):
        for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
            for _ in range(2):
                response = employee_client.get(archive_url(candidate), **headers)
                assert response.status_code == 200

    assert list(Candidate.objects.order_by("pk").values()) == candidates_before
    assert applications_state() == apps_before


def test_confirmation_for_archived_candidate_offers_no_archive(employee_client):
    sam = make_candidate("Sam", archived=True)

    for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
        page = employee_client.get(archive_url(sam), **headers).content.decode()
        assert "already archived" in page
        assert f'action="{archive_url(sam)}"' not in page
        assert re.search(r'<form\b[^>]*method="dialog"', page)


# --- Lists and editing ------------------------------------------------------


def test_archived_list_empty_state_and_link_back(employee_client):
    jane = make_candidate("Jane")

    page = employee_client.get("/candidates/?archived=1").content.decode()

    assert "Archived candidates" in page
    assert "No archived candidates." in page
    assert f'href="/candidates/{jane.pk}/"' not in page
    match = re.search(r'<a href="(/candidates/)"[^>]*>Show active candidates</a>', page)
    assert match
    active = employee_client.get(match.group(1)).content.decode()
    assert f'href="/candidates/{jane.pk}/"' in active


def test_editing_an_archived_candidate_keeps_them_archived(employee_client):
    sam = make_candidate("Sam", archived=True)

    response = employee_client.post(
        f"/candidates/{sam.pk}/edit/",
        {
            "first_name": "Samuel",
            "last_name": "Doe",
            "email": "sam@example.com",
            "source": Source.REFERRAL,
            "is_archived": "",  # forged: not a form field, must be ignored
        },
    )

    assert response.status_code == 302
    sam.refresh_from_db()
    assert sam.first_name == "Samuel"
    assert sam.is_archived is True


# --- Candidate detail template structure ------------------------------------


def form_nesting_depth(page):
    depth = deepest = 0
    for tag in re.findall(r"</?form\b", page):
        depth += -1 if tag.startswith("</") else 1
        deepest = max(deepest, depth)
        assert depth >= 0
    assert depth == 0
    return deepest


@pytest.mark.parametrize("archived", [False, True])
def test_candidate_detail_has_no_duplicates_or_nested_forms(employee_client, archived):
    sam = make_candidate("Sam", archived=archived)

    page = employee_client.get(f"/candidates/{sam.pk}/").content.decode()

    assert len(re.findall(r"<h1\b", page)) == 1
    assert len(re.findall(r"<h2\b[^>]*>Applications</h2>", page)) == 1
    assert form_nesting_depth(page) <= 1
    expected = {
        ">Edit</a>": 1,
        ">Delete</a>": 1,
        ">All candidates</a>": 1,
        ">Archive</a>": 0 if archived else 1,
        ">Add application</a>": 0 if archived else 1,
        ">Unarchive</button>": 1 if archived else 0,
        ">Archived</span>": 1 if archived else 0,
    }
    assert {label: page.count(label) for label in expected} == expected
