"""Phase 8 Test 2: ``Application.move_to(to_stage, employee, expected_stage,
expected_changed_at)`` (the timestamp became required in Phase 9)."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import hiring.models
from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import Application, Stage
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
LONG_AGO = timezone.now() - datetime.timedelta(days=3)


def api():
    """(move_to check, InvalidMove, StaleMove); missing pieces fail as assertions."""
    assert callable(getattr(Application, "move_to", None)), "no Application.move_to"
    invalid = getattr(hiring.models, "InvalidMove", None)
    stale = getattr(hiring.models, "StaleMove", None)
    assert isinstance(invalid, type), "no hiring.models.InvalidMove"
    assert isinstance(stale, type), "no hiring.models.StaleMove"
    assert issubclass(stale, invalid)
    return invalid, stale


@pytest.fixture
def recruiter(django_user_model):
    return django_user_model.objects.create_user(username="recruiter")


@pytest.fixture
def mover(django_user_model):
    return django_user_model.objects.create_user(username="mover")


def make_application(recruiter, stage, *, first="Ana", opening=None):
    """An application last changed long ago, so a new change is visible."""
    application = Application.objects.create(
        candidate=Candidate.objects.create(
            first_name=first,
            last_name="Doe",
            email=f"{first.lower()}@example.com",
            source=Source.REFERRAL,
        ),
        opening=opening or JobOpening.objects.create(title="Analyst", department="IT"),
        stage=stage,
        previous_stage=S.APPLIED if stage != S.APPLIED else None,
        stage_changed_by=recruiter,
    )
    Application.objects.filter(pk=application.pk).update(
        stage_changed_at=LONG_AGO, updated_at=LONG_AGO
    )
    application.refresh_from_db()
    return application


def row(application):
    return Application.objects.filter(pk=application.pk).values().get()


def everything():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


# --- Valid moves ------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "to"),
    [
        (S.APPLIED, S.SCREENING),  # advance
        (S.APPLIED, S.OFFER),  # skip
        (S.INTERVIEW, S.REJECTED),  # end
        (S.FINAL_REVIEW, S.WITHDRAWN),  # end
        (S.OFFER, S.HIRED),  # hire
    ],
)
def test_valid_move_records_stage_previous_stage_who_and_when(
    recruiter, mover, start, to
):
    api()
    application = make_application(recruiter, start)
    bystander = make_application(recruiter, S.SCREENING, first="Ben")
    others_before = [
        list(Application.objects.exclude(pk=application.pk).order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    ]
    before = row(application)
    started = timezone.now()

    application.move_to(
        to,
        mover,
        expected_stage=start,
        expected_changed_at=application.stage_changed_at,
    )

    after = row(application)
    assert after["stage"] == to
    assert after["previous_stage"] == start  # the stage it actually left
    assert after["stage_changed_by_id"] == mover.pk
    assert after["stage_changed_at"] >= started > LONG_AGO
    assert after["updated_at"] >= started
    # Nothing else on the application changes.
    changed = {"stage", "previous_stage", "stage_changed_by_id"}
    changed |= {"stage_changed_at", "updated_at"}
    assert {k: v for k, v in after.items() if k not in changed} == {
        k: v for k, v in before.items() if k not in changed
    }
    # The in-memory object reflects the saved move.
    assert (application.stage, application.previous_stage) == (to, start)
    assert application.stage_changed_by_id == mover.pk
    # Unrelated applications, candidates, and openings are untouched.
    assert [
        list(Application.objects.exclude(pk=application.pk).order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    ] == others_before
    assert row(bystander)["stage"] == S.SCREENING


# --- Invalid moves ----------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "to"),
    [
        (from_stage, to_stage)
        for from_stage in Stage
        for to_stage in Stage
        if rules.why_not(from_stage, to_stage) is not None
    ],
    ids=lambda s: s.value,
)
def test_every_invalid_move_raises_and_changes_nothing(recruiter, mover, start, to):
    invalid, stale = api()
    application = make_application(recruiter, start)
    before = everything()

    with pytest.raises(invalid) as caught:
        application.move_to(
            to,
            mover,
            expected_stage=start,
            expected_changed_at=application.stage_changed_at,
        )

    assert not isinstance(caught.value, stale)
    assert str(caught.value) == rules.why_not(start, to)  # the rules' reason
    assert everything() == before


@pytest.mark.parametrize("start", [S.APPLIED, S.SCREENING, S.INTERVIEW, S.FINAL_REVIEW])
def test_hired_only_from_offer(recruiter, mover, start):
    invalid, _ = api()
    application = make_application(recruiter, start)

    with pytest.raises(invalid, match="Hired can only be reached from Offer"):
        application.move_to(
            S.HIRED,
            mover,
            expected_stage=start,
            expected_changed_at=application.stage_changed_at,
        )
    assert row(application)["stage"] == start

    offer = make_application(recruiter, S.OFFER, first="Ben")
    offer.move_to(
        S.HIRED,
        mover,
        expected_stage=S.OFFER,
        expected_changed_at=offer.stage_changed_at,
    )
    assert row(offer)["stage"] == S.HIRED


def test_unknown_stage_value_is_an_invalid_move(recruiter, mover):
    invalid, stale = api()
    application = make_application(recruiter, S.APPLIED)
    before = everything()

    with pytest.raises(invalid) as caught:
        application.move_to(
            "promoted",
            mover,
            expected_stage=S.APPLIED,
            expected_changed_at=application.stage_changed_at,
        )

    assert not isinstance(caught.value, stale)
    assert str(caught.value)
    assert everything() == before


# --- Stale moves ------------------------------------------------------------


def test_stale_move_cannot_overwrite_a_newer_change(recruiter, mover):
    """Two employees opened the modal at Applied; the second confirm is stale."""
    _, stale = api()
    application = make_application(recruiter, S.APPLIED)
    first_view = Application.objects.get(pk=application.pk)
    second_view = Application.objects.get(pk=application.pk)  # same old stage

    first_view.move_to(
        S.SCREENING,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=first_view.stage_changed_at,
    )
    newer = everything()

    # Interview would be a valid move from Screening, yet it must be refused.
    with pytest.raises(stale) as caught:
        second_view.move_to(
            S.INTERVIEW,
            mover,
            expected_stage=S.APPLIED,
            expected_changed_at=second_view.stage_changed_at,
        )

    message = str(caught.value)
    assert "Screening" in message  # where it actually is now
    assert "changed" in message.lower()
    assert everything() == newer  # stage, previous stage, who and when all kept
    assert row(application)["stage_changed_by_id"] == recruiter.pk


@pytest.mark.parametrize(
    ("expected", "to"),
    [
        (S.SCREENING, S.INTERVIEW),  # would be valid from the claimed stage
        (S.SCREENING, S.APPLIED),  # invalid as well as stale: stale wins
        ("bogus", S.OFFER),  # an expected stage that isn't a stage
    ],
)
def test_expected_stage_mismatch_is_stale(recruiter, mover, expected, to):
    _, stale = api()
    application = make_application(recruiter, S.APPLIED)
    before = everything()

    with pytest.raises(stale):
        application.move_to(
            to,
            mover,
            expected_stage=expected,
            expected_changed_at=application.stage_changed_at,
        )

    assert everything() == before


def test_both_confirmations_of_the_same_old_stage_cannot_succeed(recruiter, mover):
    """Exactly one of two moves from the same expected stage wins."""
    _, stale = api()
    application = make_application(recruiter, S.INTERVIEW)
    views = [Application.objects.get(pk=application.pk) for _ in range(2)]

    outcomes = []
    for view, (to, who) in zip(
        views, [(S.OFFER, recruiter), (S.REJECTED, mover)], strict=True
    ):
        try:
            view.move_to(
                to,
                who,
                expected_stage=S.INTERVIEW,
                expected_changed_at=view.stage_changed_at,
            )
            outcomes.append("moved")
        except stale:
            outcomes.append("stale")

    assert outcomes == ["moved", "stale"]
    final = row(application)
    assert (final["stage"], final["previous_stage"]) == (S.OFFER, S.INTERVIEW)
    assert final["stage_changed_by_id"] == recruiter.pk


def test_stage_check_and_update_are_one_conditional_update(recruiter, mover):
    """The expected-stage check happens inside the UPDATE itself, so no other
    write can land between checking and saving."""
    api()
    application = make_application(recruiter, S.APPLIED)

    with CaptureQueriesContext(connection) as queries:
        application.move_to(
            S.SCREENING,
            mover,
            expected_stage=S.APPLIED,
            expected_changed_at=application.stage_changed_at,
        )

    writes = [
        q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("UPDATE")
    ]
    assert len(writes) == 1, writes
    where = writes[0].upper().split(" WHERE ", 1)[1]
    assert '"STAGE"' in where, writes[0]
    assert not [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "DELETE"))
    ]
