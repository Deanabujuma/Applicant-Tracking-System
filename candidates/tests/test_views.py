import pytest
from django.urls import reverse

from candidates.models import Candidate, Source


@pytest.fixture
def employee_client(client, django_user_model):
    """A client logged in as an ordinary active hiring employee."""
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


@pytest.mark.django_db
def test_create_candidate_with_only_required_fields(employee_client):
    """Only first name, last name, email, and source are needed to start tracking someone."""
    response = employee_client.post(
        "/candidates/new/",
        {
            "first_name": "Ana",
            "last_name": "Lopez",
            "email": "  Ana.Lopez@Example.com  ",
            "source": Source.JOB_BOARD,
            "phone": "",
            "source_detail": "",
            "notes": "",
        },
    )

    assert response.status_code == 302
    candidate = Candidate.objects.get()
    assert response.url == f"/candidates/{candidate.pk}/"
    assert candidate.first_name == "Ana"
    assert candidate.last_name == "Lopez"
    assert candidate.email == "Ana.Lopez@Example.com"  # trimmed, case kept
    assert candidate.source == Source.JOB_BOARD
    assert candidate.phone == ""
    assert candidate.source_detail == ""
    assert candidate.notes == ""
    assert candidate.is_archived is False

    detail = employee_client.get(response.url)
    assert detail.status_code == 200
    page = detail.content.decode()
    assert "Ana" in page
    assert "Lopez" in page
    assert "Ana.Lopez@Example.com" in page
    assert "Job Board" in page


@pytest.mark.django_db
def test_duplicate_email_is_rejected_with_link_to_existing_candidate(employee_client):
    """A case-only duplicate email is refused, and the employee is pointed to the existing record."""
    existing = Candidate.objects.create(
        first_name="<script>alert(1)</script>",
        last_name="Lopez",
        email="Ana.Lopez@Example.com",
        source=Source.JOB_BOARD,
    )

    response = employee_client.post(
        reverse("candidates:create"),
        {
            "first_name": "Ana",
            "last_name": "Lopez",
            "email": "ANA.LOPEZ@example.com",
            "source": Source.REFERRAL,
        },
    )

    # Nothing new is saved; the form is shown again with the error.
    assert response.status_code == 200
    assert Candidate.objects.count() == 1
    page = response.content.decode()
    assert "A candidate with this email already exists." in page

    # The error links to the existing candidate's detail page...
    existing_url = reverse("candidates:detail", kwargs={"pk": existing.pk})
    assert f'href="{existing_url}"' in page
    assert employee_client.get(existing_url).status_code == 200

    # ...and the existing record's data is escaped, never injected as raw HTML.
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
