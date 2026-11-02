"""Phase 6 Test 3: the employee-facing Archive and Unarchive workflow."""

import re

import pytest
from django.test import Client
from django.utils.html import escape

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


def make_candidate(first):
    return Candidate.objects.create(
        first_name=first,
        last_name="Doe",
        email=f"{first.lower()}@example.com",
        source=Source.REFERRAL,
    )


def is_archived(candidate):
    return Candidate.objects.get(pk=candidate.pk).is_archived


def applications_state():
    return list(Application.objects.order_by("pk").values())


def post_forms_to(page, url):
    return re.findall(
        rf'<form\b[^>]*method="post"[^>]*action="{url}"[^>]*>.*?</form>',
        page,
        re.DOTALL,
    )


def cancel_forms(page):
    return re.findall(r'<form\b[^>]*method="dialog"[^>]*>(.*?)</form>', page, re.DOTALL)


def lists_candidate(page, candidate):
    return f'href="/candidates/{candidate.pk}/"' in page


def test_archive_and_unarchive_pages(django_user_model):
    employee = django_user_model.objects.create_user(username="jsmith")
    client = Client(enforce_csrf_checks=True)  # real CSRF checking throughout
    client.force_login(employee)

    analyst = JobOpening.objects.create(title="Data Analyst", department="Fin")
    engineer = JobOpening.objects.create(title="Data Engineer", department="IT")
    jane, sam, bob = (
        make_candidate("Jane"),
        make_candidate("Sam"),
        make_candidate("Bob"),
    )
    for candidate, opening, stage in [
        (jane, analyst, Stage.INTERVIEW),  # active: blocks archiving Jane
        (jane, engineer, Stage.REJECTED),  # closed: doesn't block
        (sam, analyst, Stage.HIRED),  # Sam: only closed applications
        (bob, engineer, Stage.OFFER),  # unrelated
    ]:
        Application.objects.create(
            candidate=candidate, opening=opening, stage=stage, stage_changed_by=employee
        )
    apps_before = applications_state()

    def token(page):
        return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)

    # Jane's detail page offers Archive, which loads a confirmation into #modal.
    jane_archive = f"/candidates/{jane.pk}/archive/"
    detail = client.get(f"/candidates/{jane.pk}/").content.decode()
    assert f'hx-get="{jane_archive}"' in detail

    # Jane's confirmation (HTMX and full page) lists the blocker and can't confirm.
    for headers in ({"HTTP_HX_REQUEST": "true"}, {}):
        response = client.get(jane_archive, **headers)
        assert response.status_code == 200
        page = response.content.decode()
        assert ("<html" in page.lower()) == (not headers)  # fragment vs full page
        assert f"#{analyst.pk} Data Analyst" in page
        assert "Interview" in page
        assert "Data Engineer" not in page  # the Rejected one doesn't block
        assert post_forms_to(page, jane_archive) == []  # no Archive confirmation
        assert len(cancel_forms(page)) == 1
    assert not is_archived(jane)

    # A forged/direct POST is checked again and refused, naming the blocker.
    response = client.post(
        jane_archive, {"csrfmiddlewaretoken": token(detail)}, follow=True
    )
    assert response.redirect_chain == [(f"/candidates/{jane.pk}/", 302)]
    page = response.content.decode()
    assert "alert-error" in page
    assert escape("Jane Doe can't be archived") in page
    assert f"#{analyst.pk} Data Analyst (Interview)" in page
    assert not is_archived(jane)
    assert applications_state() == apps_before

    # Sam's confirmation offers a CSRF-protected Archive and a Cancel.
    sam_archive = f"/candidates/{sam.pk}/archive/"
    for headers in ({"HTTP_HX_REQUEST": "true"}, {}):
        page = client.get(sam_archive, **headers).content.decode()
        [form] = post_forms_to(page, sam_archive)
        assert 'name="csrfmiddlewaretoken"' in form
        assert len(cancel_forms(page)) == 1
    assert not is_archived(sam)  # GETs never archive

    # Confirmed archive: Sam leaves the default list and appears under archived.
    response = client.post(
        sam_archive, {"csrfmiddlewaretoken": token(page)}, follow=True
    )
    assert response.redirect_chain == [(f"/candidates/{sam.pk}/", 302)]
    assert "alert-success" in response.content.decode()
    assert is_archived(sam)
    active_list = client.get("/candidates/").content.decode()
    assert not lists_candidate(active_list, sam)
    assert lists_candidate(active_list, jane)
    assert 'href="/candidates/?archived=1"' in active_list
    archived_list = client.get("/candidates/?archived=1").content.decode()
    assert lists_candidate(archived_list, sam)
    assert not lists_candidate(archived_list, jane)
    assert 'href="/candidates/"' in archived_list

    # Sam's page: Unarchive (POST + CSRF) instead of Archive or Add application.
    sam_unarchive = f"/candidates/{sam.pk}/unarchive/"
    detail = client.get(f"/candidates/{sam.pk}/").content.decode()
    [form] = post_forms_to(detail, sam_unarchive)
    assert 'name="csrfmiddlewaretoken"' in form
    assert sam_archive not in detail
    assert "/applications/new/" not in detail

    # Unarchive refuses GET and token-less POSTs; a proper POST restores Sam.
    assert client.get(sam_unarchive).status_code == 405
    assert client.post(sam_unarchive).status_code == 403
    assert is_archived(sam)
    response = client.post(sam_unarchive, {"csrfmiddlewaretoken": token(detail)})
    assert response.status_code == 302
    assert not is_archived(sam)
    assert lists_candidate(client.get("/candidates/").content.decode(), sam)

    # Nothing else changed: every application and the other candidates.
    assert applications_state() == apps_before
    assert not is_archived(jane)
    assert not is_archived(bob)
