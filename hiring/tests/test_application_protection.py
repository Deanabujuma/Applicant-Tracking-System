"""Phase 5 Test 1: the database protects candidates and openings with applications."""

import pytest
from django.db.models import ProtectedError

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


def state(application):
    """What must survive every refused deletion: all three rows and their links."""
    application = Application.objects.filter(pk=application.pk).first()
    if application is None:
        return None
    return {
        "candidate": Candidate.objects.filter(pk=application.candidate_id).exists(),
        "opening": JobOpening.objects.filter(pk=application.opening_id).exists(),
        "candidate_id": application.candidate_id,
        "opening_id": application.opening_id,
        "stage": application.stage,
        "candidate_applications": list(
            Candidate.objects.get(pk=application.candidate_id).applications.all()
        ),
        "opening_applications": list(
            JobOpening.objects.get(pk=application.opening_id).applications.all()
        ),
    }


def test_records_with_applications_cannot_be_deleted_directly(django_user_model):
    employee = django_user_model.objects.create_user(username="jsmith")
    candidate = Candidate.objects.create(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        source=Source.REFERRAL,
    )
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    application = Application.objects.create(
        candidate=candidate, opening=opening, stage_changed_by=employee
    )
    before = state(application)
    assert before["candidate_applications"] == [application]
    assert before["stage"] == Stage.APPLIED
    assert application.previous_stage is None  # nothing to undo yet

    attempts = {
        "candidate.delete()": lambda: Candidate.objects.get(pk=candidate.pk).delete(),
        "opening.delete()": lambda: JobOpening.objects.get(pk=opening.pk).delete(),
        "Candidate queryset .delete()": lambda: Candidate.objects.filter(
            pk=candidate.pk
        ).delete(),
        "JobOpening queryset .delete()": lambda: JobOpening.objects.filter(
            pk=opening.pk
        ).delete(),
    }
    for description, attempt in attempts.items():
        with pytest.raises(ProtectedError):
            attempt()
        assert state(application) == before, f"{description} changed data"
