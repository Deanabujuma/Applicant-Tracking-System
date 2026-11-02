"""Phase 6 Test 2: Candidate.archive() is refused while active applications exist.

Lives with hiring's tests because it needs Application records; the code under
test (Candidate.archive) is in candidates and must not import hiring.
"""

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


def make_candidate(first):
    return Candidate.objects.create(
        first_name=first,
        last_name="Doe",
        email=f"{first.lower()}@example.com",
        phone="555-0100",
        source=Source.REFERRAL,
        notes="Strong portfolio.",
    )


def candidate_state(candidate):
    """Every stored candidate field, read fresh."""
    return Candidate.objects.filter(pk=candidate.pk).values().get()


def applications_state():
    return list(Application.objects.order_by("pk").values())


def test_archive_refused_while_active_applications_exist(django_user_model):
    employee = django_user_model.objects.create_user(username="jsmith")
    openings = {
        title: JobOpening.objects.create(title=title, department="IT")
        for title in ("Analyst", "Engineer", "Designer", "Manager")
    }
    jane, sam, nina = (
        make_candidate("Jane"),
        make_candidate("Sam"),
        make_candidate("Nina"),
    )

    def apply(candidate, title, stage):
        return Application.objects.create(
            candidate=candidate,
            opening=openings[title],
            stage=stage,
            stage_changed_by=employee,
        )

    # Jane: two active applications and two completed ones.
    interview = apply(jane, "Analyst", Stage.INTERVIEW)
    offer = apply(jane, "Engineer", Stage.OFFER)
    apply(jane, "Designer", Stage.REJECTED)
    apply(jane, "Manager", Stage.WITHDRAWN)
    # Sam: only completed applications. Nina: none.
    apply(sam, "Analyst", Stage.HIRED)
    apply(sam, "Engineer", Stage.REJECTED)
    apply(sam, "Designer", Stage.WITHDRAWN)

    jane_before, apps_before = candidate_state(jane), applications_state()

    assert callable(getattr(jane, "archive", None)), "Candidate has no archive() method"

    # Refused: it reports exactly the blocking (active) applications...
    blocking = jane.archive()
    assert set(blocking) == {interview, offer}
    assert {(a.opening.title, a.stage) for a in blocking} == {
        ("Analyst", Stage.INTERVIEW),
        ("Engineer", Stage.OFFER),
    }
    # ...and changes nothing at all.
    assert candidate_state(jane) == jane_before
    assert candidate_state(jane)["is_archived"] is False
    assert applications_state() == apps_before

    # All applications completed: archived. Only is_archived and updated_at change.
    for candidate in (sam, nina):  # Nina has no applications at all
        before = candidate_state(candidate)
        assert list(candidate.archive()) == []
        after = candidate_state(candidate)
        assert after["is_archived"] is True
        # (>=, not >: the clock may not tick between creating and archiving)
        assert after["updated_at"] >= before["updated_at"]
        assert {
            k: v for k, v in after.items() if k not in ("is_archived", "updated_at")
        } == {k: v for k, v in before.items() if k not in ("is_archived", "updated_at")}
        assert applications_state() == apps_before  # stages never change

        # Archiving again: nothing to do, nothing saved.
        assert list(Candidate.objects.get(pk=candidate.pk).archive()) == []
        assert candidate_state(candidate) == after
        assert applications_state() == apps_before
