"""Phase 6 Test 1: hiring's single definition of an "active" application."""

import pytest
from django.db.models import QuerySet

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

ACTIVE = {
    Stage.APPLIED,
    Stage.SCREENING,
    Stage.INTERVIEW,
    Stage.FINAL_REVIEW,
    Stage.OFFER,
}
CLOSED = {Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN}


def test_active_returns_only_applied_through_offer(django_user_model):
    employee = django_user_model.objects.create_user(username="jsmith")
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    other = JobOpening.objects.create(title="Backend Dev", department="IT")
    jane = Candidate.objects.create(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        source=Source.REFERRAL,
    )
    # One application in every stage, all to Data Analyst...
    by_stage = {}
    for stage in Stage:
        candidate = Candidate.objects.create(
            first_name=stage.label,
            last_name="Applicant",
            email=f"{stage.value}@example.com",
            source=Source.REFERRAL,
        )
        by_stage[stage] = Application.objects.create(
            candidate=candidate, opening=analyst, stage=stage, stage_changed_by=employee
        )
    # ...plus Jane with one active and one closed application.
    jane_active = Application.objects.create(
        candidate=jane,
        opening=analyst,
        stage=Stage.INTERVIEW,
        stage_changed_by=employee,
    )
    Application.objects.create(
        candidate=jane, opening=other, stage=Stage.REJECTED, stage_changed_by=employee
    )
    assert set(by_stage) == ACTIVE | CLOSED  # all eight stages are covered
    before = list(Application.objects.order_by("pk").values())

    assert callable(getattr(Application.objects, "active", None)), (
        "Application.objects has no active() method"
    )
    active = Application.objects.active()

    # Exactly the Applied-through-Offer applications, as real Application rows.
    assert isinstance(active, QuerySet)
    assert set(active) == {by_stage[s] for s in ACTIVE} | {jane_active}
    assert all(isinstance(a, Application) for a in active)
    assert not active.filter(stage__in=CLOSED).exists()

    # Chainable in both directions, and through the reverse relations.
    assert set(active.filter(opening=other)) == set()
    assert active.order_by("pk").count() == 6
    assert set(Application.objects.filter(candidate=jane).active()) == {jane_active}
    assert list(jane.applications.active()) == [jane_active]
    assert analyst.applications.active().count() == 6

    # Querying never modifies anything.
    assert list(Application.objects.order_by("pk").values()) == before
