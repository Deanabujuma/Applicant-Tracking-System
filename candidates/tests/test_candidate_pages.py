"""Phase 2 candidate pages: list, edit, source choices, and login protection."""

import pytest
from django.urls import reverse

from candidates.models import Candidate, Source

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee_client(client, django_user_model):
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


def make_candidate(**overrides):
    fields = {
        "first_name": "Ana",
        "last_name": "Lopez",
        "email": "ana.lopez@example.com",
        "source": Source.JOB_BOARD,
    }
    fields.update(overrides)
    return Candidate.objects.create(**fields)


def form_data(candidate, **overrides):
    """The candidate's current values as the edit form would post them."""
    data = {
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "source": candidate.source,
        "source_detail": candidate.source_detail,
        "notes": candidate.notes,
    }
    data.update(overrides)
    return data


def required_fields(**overrides):
    data = {
        "first_name": "Ana",
        "last_name": "Lopez",
        "email": "a@example.com",
        "source": Source.OTHER,
    }
    data.update(overrides)
    return data


# --- Source choices ---------------------------------------------------------


@pytest.mark.parametrize("source", Source.values)
def test_each_fixed_source_is_accepted(employee_client, source):
    response = employee_client.post(
        reverse("candidates:create"), required_fields(source=source)
    )

    assert response.status_code == 302
    assert Candidate.objects.get().source == source


def test_source_outside_the_fixed_list_is_rejected(employee_client):
    response = employee_client.post(
        reverse("candidates:create"), required_fields(source="LinkedIn")
    )

    assert response.status_code == 200
    assert "source" in response.context["form"].errors
    assert Candidate.objects.count() == 0


def test_source_is_required(employee_client):
    response = employee_client.post(
        reverse("candidates:create"), required_fields(source="")
    )

    assert response.status_code == 200
    assert "source" in response.context["form"].errors
    assert Candidate.objects.count() == 0


def test_source_detail_records_specific_origin(employee_client):
    employee_client.post(
        reverse("candidates:create"),
        required_fields(source=Source.REFERRAL, source_detail="Referred by J. Smith"),
    )

    candidate = Candidate.objects.get()
    page = employee_client.get(candidate.get_absolute_url()).content.decode()
    assert "Referral (Referred by J. Smith)" in page


# --- List -------------------------------------------------------------------


def test_list_orders_by_last_name_first_name_then_pk(employee_client):
    zed = make_candidate(first_name="Zed", last_name="Adams", email="zed@example.com")
    lopez_older = make_candidate(email="ana2@example.com")
    lopez_newer = make_candidate(email="ana1@example.com")
    bea = make_candidate(first_name="Bea", last_name="Adams", email="bea@example.com")

    response = employee_client.get(reverse("candidates:list"))

    assert response.status_code == 200
    assert list(response.context["candidate_list"]) == [
        bea,
        zed,
        lopez_older,
        lopez_newer,
    ]


def test_list_links_each_candidate_to_their_detail_page(employee_client):
    candidate = make_candidate()

    page = employee_client.get(reverse("candidates:list")).content.decode()

    assert f'href="{candidate.get_absolute_url()}"' in page
    assert "ana.lopez@example.com" in page
    assert "Job Board" in page


def test_header_has_candidates_link(employee_client):
    page = employee_client.get(reverse("hiring:workspace")).content.decode()

    assert f'href="{reverse("candidates:list")}"' in page


# --- Edit -------------------------------------------------------------------


def test_edit_updates_details_and_list_and_detail_reflect_it(employee_client):
    candidate = make_candidate()
    edit_url = reverse("candidates:edit", kwargs={"pk": candidate.pk})

    response = employee_client.post(
        edit_url,
        form_data(candidate, last_name="Lopez-Garcia", phone="806-555-0100"),
    )

    assert response.status_code == 302
    assert response.url == candidate.get_absolute_url()
    candidate.refresh_from_db()
    assert candidate.last_name == "Lopez-Garcia"
    assert candidate.phone == "806-555-0100"
    detail = employee_client.get(candidate.get_absolute_url()).content.decode()
    assert "Lopez-Garcia" in detail
    assert "806-555-0100" in detail
    listing = employee_client.get(reverse("candidates:list")).content.decode()
    assert "Lopez-Garcia, Ana" in listing


def test_edit_page_is_prefilled_with_current_values(employee_client):
    candidate = make_candidate(phone="806-555-0100")

    response = employee_client.get(
        reverse("candidates:edit", kwargs={"pk": candidate.pk})
    )

    assert response.status_code == 200
    page = response.content.decode()
    assert 'value="ana.lopez@example.com"' in page
    assert 'value="806-555-0100"' in page


def test_edit_keeping_own_email_is_not_a_duplicate(employee_client):
    candidate = make_candidate(email="Ana.Lopez@Example.com")
    edit_url = reverse("candidates:edit", kwargs={"pk": candidate.pk})

    unchanged = employee_client.post(
        edit_url, form_data(candidate, notes="Strong portfolio")
    )
    recased = employee_client.post(
        edit_url,
        form_data(candidate, email="ana.lopez@example.com", notes="Strong portfolio"),
    )

    assert unchanged.status_code == 302
    assert recased.status_code == 302
    candidate.refresh_from_db()
    assert candidate.notes == "Strong portfolio"
    assert candidate.email == "ana.lopez@example.com"
    assert Candidate.objects.count() == 1


def test_edit_to_another_candidates_email_is_rejected_with_link(employee_client):
    other = make_candidate(
        first_name="Bea", last_name="Adams", email="bea.adams@example.com"
    )
    candidate = make_candidate()
    edit_url = reverse("candidates:edit", kwargs={"pk": candidate.pk})

    response = employee_client.post(
        edit_url, form_data(candidate, email="BEA.ADAMS@example.com")
    )

    assert response.status_code == 200
    page = response.content.decode()
    assert "A candidate with this email already exists." in page
    assert f'href="{other.get_absolute_url()}"' in page
    candidate.refresh_from_db()
    assert candidate.email == "ana.lopez@example.com"


# --- Login required ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "needs_pk"),
    [("list", False), ("create", False), ("detail", True), ("edit", True)],
)
def test_every_candidate_page_requires_login(client, name, needs_pk):
    kwargs = {"pk": make_candidate().pk} if needs_pk else {}
    url = reverse(f"candidates:{name}", kwargs=kwargs)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"


def test_anonymous_post_cannot_create_a_candidate(client):
    response = client.post(reverse("candidates:create"), required_fields())

    assert response.status_code == 302
    assert Candidate.objects.count() == 0


def test_anonymous_post_cannot_edit_a_candidate(client):
    candidate = make_candidate()

    response = client.post(
        reverse("candidates:edit", kwargs={"pk": candidate.pk}),
        form_data(candidate, last_name="Changed"),
    )

    assert response.status_code == 302
    candidate.refresh_from_db()
    assert candidate.last_name == "Lopez"
