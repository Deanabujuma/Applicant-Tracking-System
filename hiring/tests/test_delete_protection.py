"""Phase 5 Test 3: employee-facing deletes refuse records that have applications."""

import re

import pytest
from django.utils.html import escape

from candidates.models import Candidate, Source
from hiring.models import Application
from openings.models import JobOpening, Skill

pytestmark = pytest.mark.django_db


def make_candidate(first):
    return Candidate.objects.create(
        first_name=first,
        last_name="Doe",
        email=f"{first.lower()}@example.com",
        source=Source.REFERRAL,
    )


def everything():
    """Every candidate, opening, skill, application, and link, by ID."""
    return {
        "candidates": set(Candidate.objects.values_list("pk", "email")),
        "openings": set(JobOpening.objects.values_list("pk", "title", "updated_at")),
        "skills": set(Skill.objects.values_list("pk", "name")),
        "applications": set(
            Application.objects.values_list("pk", "candidate_id", "opening_id", "stage")
        ),
        "skill_links": set(
            JobOpening.skills.through.objects.values_list("jobopening_id", "skill_id")
        ),
    }


def test_deletes_are_refused_when_applications_exist(client, django_user_model):
    employee = django_user_model.objects.create_user(username="jsmith")
    client.force_login(employee)
    # An employee would see a server error page if a delete crashed; make the
    # test client return that page as a response instead of re-raising.
    client.raise_request_exception = False

    jane, bob, ann = (
        make_candidate("Jane"),
        make_candidate("Bob"),
        make_candidate("Ann"),
    )
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    backend = JobOpening.objects.create(title="Backend Dev", department="IT")
    analyst.skills.add(Skill.objects.create(name="Python"))
    Application.objects.create(
        candidate=jane, opening=analyst, stage_changed_by=employee
    )
    Application.objects.create(
        candidate=ann, opening=backend, stage_changed_by=employee
    )
    before = everything()

    # Opening with an application: the confirmed Delete POST is refused.
    response = client.post(f"/openings/{analyst.pk}/delete/", follow=True)
    assert response.status_code == 200  # not a server error
    assert response.redirect_chain == [(f"/openings/{analyst.pk}/", 302)]
    refused = (
        f"Opening #{analyst.pk} Data Analyst has applications, "
        "so it can't be deleted. Close it instead."
    )
    page = response.content.decode()
    assert "alert-error" in page
    assert escape(refused) in page
    assert everything() == before

    # Candidate delete confirmation: read-only GET, POST form with CSRF, Cancel.
    url = f"/candidates/{jane.pk}/delete/"
    for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
        response = client.get(url, **headers)
        assert response.status_code == 200
        page = response.content.decode()
        assert "Jane Doe" in page
        post_forms = re.findall(
            rf'<form\b[^>]*method="post"[^>]*action="{url}"[^>]*>.*?</form>',
            page,
            re.DOTALL,
        )
        assert len(post_forms) == 1
        assert 'name="csrfmiddlewaretoken"' in post_forms[0]
        cancel = re.findall(
            r'<form\b[^>]*method="dialog"[^>]*>(.*?)</form>', page, re.DOTALL
        )
        assert len(cancel) == 1
        assert "Cancel" in cancel[0]
    detail = client.get(f"/candidates/{jane.pk}/").content.decode()
    assert f'hx-get="{url}"' in detail  # the detail page offers Delete
    assert everything() == before

    # Candidate with an application: the confirmed Delete POST is refused.
    response = client.post(url, follow=True)
    assert response.status_code == 200
    assert response.redirect_chain == [(f"/candidates/{jane.pk}/", 302)]
    page = response.content.decode()
    assert "alert-error" in page
    assert escape("Jane Doe has applications, so they can't be deleted.") in page
    assert everything() == before

    # Candidate with no applications: deleted, and nothing else is touched.
    response = client.post(f"/candidates/{bob.pk}/delete/", follow=True)
    assert response.redirect_chain == [("/candidates/", 302)]
    page = response.content.decode()
    assert "alert-success" in page
    assert "Deleted candidate Bob Doe." in page
    after = everything()
    assert not Candidate.objects.filter(pk=bob.pk).exists()
    assert after["candidates"] == before["candidates"] - {(bob.pk, "bob@example.com")}
    assert {k: v for k, v in after.items() if k != "candidates"} == {
        k: v for k, v in before.items() if k != "candidates"
    }
