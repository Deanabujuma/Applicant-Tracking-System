"""Phase 9 Test 2: ``Application.undo(employee, expected_stage, expected_changed_at)``."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import Application, InvalidMove, Stage, StaleMove
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
LONG_AGO = timezone.now() - datetime.timedelta(days=3)


def check_api():
    assert callable(getattr(Application, "undo", None)), "no Application.undo"


@pytest.fixture
def recruiter(django_user_model):
    return django_user_model.objects.create_user(username="recruiter")


@pytest.fixture
def undoer(django_user_model):
    return django_user_model.objects.create_user(username="undoer")


@pytest.fixture
def other(django_user_model):
    return django_user_model.objects.create_user(username="other")


@pytest.fixture
def make(recruiter):
    """An application at ``stage`` with ``previous`` stored, changed long ago."""
    count = iter(range(100))

    def make_application(stage, previous=None):
        n = next(count)
        application = Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=f"Person{n}",
                last_name="Doe",
                email=f"person{n}@example.com",
                source=Source.REFERRAL,
            ),
            opening=JobOpening.objects.create(title=f"Role {n}", department="IT"),
            stage=S.APPLIED,
            stage_changed_by=recruiter,
        )
        # Set the history directly (including impossible histories on purpose).
        Application.objects.filter(pk=application.pk).update(
            stage=stage,
            previous_stage=previous,
            stage_changed_at=LONG_AGO,
            updated_at=LONG_AGO,
        )
        application.refresh_from_db()
        return application

    return make_application


def row(application):
    return Application.objects.filter(pk=application.pk).values().get()


def fresh(application):
    """A separate copy, as another employee's request would load it."""
    return Application.objects.get(pk=application.pk)


def everything():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def undo(application, employee):
    """Undo with the stage and token the employee's page would have shown."""
    application.undo(
        employee,
        expected_stage=application.stage,
        expected_changed_at=application.stage_changed_at,
    )


# --- Successful Undo --------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "to"),
    [
        (S.APPLIED, S.SCREENING),  # forward one step
        (S.APPLIED, S.OFFER),  # a skip: back to Applied, not Final Review
        (S.SCREENING, S.FINAL_REVIEW),  # a skip from mid-pipeline
        (S.INTERVIEW, S.REJECTED),
        (S.OFFER, S.REJECTED),
        (S.SCREENING, S.WITHDRAWN),
        (S.FINAL_REVIEW, S.WITHDRAWN),
    ],
)
def test_undo_returns_to_the_actual_previous_stage(recruiter, undoer, make, start, to):
    check_api()
    application = make(start)
    application.move_to(
        to,
        recruiter,
        expected_stage=start,
        expected_changed_at=application.stage_changed_at,
    )
    bystander = make(S.SCREENING, S.APPLIED)
    others_before = [
        list(Application.objects.exclude(pk=application.pk).order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    ]
    before = row(application)
    started = timezone.now()

    undo(fresh(application), undoer)

    after = row(application)
    assert after["stage"] == start  # where it really came from
    assert after["previous_stage"] is None  # so it can't be undone twice
    assert after["stage_changed_by_id"] == undoer.pk
    assert after["stage_changed_at"] >= started
    assert after["stage_changed_at"] != before["stage_changed_at"]
    assert after["updated_at"] >= started
    changed = {"stage", "previous_stage", "stage_changed_by_id"}
    changed |= {"stage_changed_at", "updated_at"}
    assert {k: v for k, v in after.items() if k not in changed} == {
        k: v for k, v in before.items() if k not in changed
    }
    assert [
        list(Application.objects.exclude(pk=application.pk).order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    ] == others_before
    assert row(bystander)["stage"] == S.SCREENING


def test_in_memory_application_matches_the_stored_row(undoer, make):
    check_api()
    application = make(S.OFFER, S.APPLIED)

    undo(application, undoer)

    stored = Application.objects.get(pk=application.pk)
    for name in ("stage", "previous_stage", "stage_changed_by_id", "stage_changed_at"):
        assert getattr(application, name) == getattr(stored, name), name
    assert application.updated_at == stored.updated_at


# --- Once per move ----------------------------------------------------------


def test_second_undo_is_refused_until_a_new_move(recruiter, undoer, make):
    check_api()
    application = make(S.APPLIED)
    application.move_to(
        S.REJECTED,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    undo(application, undoer)  # back to Applied
    after_first = everything()

    with pytest.raises(InvalidMove) as caught:
        undo(application, undoer)  # nothing left to undo
    assert not isinstance(caught.value, StaleMove)
    assert str(caught.value) == rules.undo_blocker(S.APPLIED, None)
    assert everything() == after_first

    # The reject-undo-reject loop: a new move earns a new Undo.
    application.move_to(
        S.REJECTED,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    undo(application, undoer)
    assert (row(application)["stage"], row(application)["previous_stage"]) == (
        S.APPLIED,
        None,
    )


def test_undo_after_moving_on_reverses_only_the_latest_move(recruiter, undoer, make):
    check_api()
    application = make(S.APPLIED)
    application.move_to(
        S.SCREENING,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    application.move_to(
        S.OFFER,
        recruiter,
        expected_stage=S.SCREENING,
        expected_changed_at=application.stage_changed_at,
    )

    undo(application, undoer)

    assert row(application)["stage"] == S.SCREENING  # not Applied
    with pytest.raises(InvalidMove):
        undo(application, undoer)


# --- Never undoable ---------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "previous"),
    [
        (S.HIRED, S.OFFER),  # Hired is permanent, even with a previous stage
        (S.HIRED, None),
        (S.APPLIED, None),  # never moved
        (S.SCREENING, None),  # already undone
        (S.SCREENING, S.WITHDRAWN),  # impossible: nothing leaves Withdrawn
        (S.APPLIED, S.SCREENING),  # impossible: nothing moves into Applied
        (S.INTERVIEW, S.OFFER),  # impossible: a backward "move"
        (S.REJECTED, S.HIRED),  # impossible: nothing leaves Hired
    ],
)
def test_ineligible_undo_raises_and_changes_nothing(undoer, make, stage, previous):
    check_api()
    application = make(stage, previous)
    before = everything()

    with pytest.raises(InvalidMove) as caught:
        undo(application, undoer)

    assert not isinstance(caught.value, StaleMove)
    assert str(caught.value) == rules.undo_blocker(stage, previous)  # the rules' reason
    assert everything() == before


def test_hired_after_a_real_offer_is_never_undoable(recruiter, undoer, make):
    check_api()
    application = make(S.OFFER, S.FINAL_REVIEW)
    application.move_to(
        S.HIRED,
        recruiter,
        expected_stage=S.OFFER,
        expected_changed_at=application.stage_changed_at,
    )
    assert row(application)["previous_stage"] == S.OFFER
    before = everything()

    with pytest.raises(InvalidMove, match="permanent"):
        undo(fresh(application), undoer)

    assert everything() == before


# --- Stale Undo -------------------------------------------------------------


def test_stale_undo_after_another_employee_moved_it(recruiter, undoer, other, make):
    check_api()
    application = make(S.APPLIED)
    application.move_to(
        S.SCREENING,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    shown = fresh(application)  # the page with the Undo button

    other_view = fresh(application)
    other_view.move_to(
        S.INTERVIEW,
        other,
        expected_stage=S.SCREENING,
        expected_changed_at=other_view.stage_changed_at,
    )
    newer = everything()

    with pytest.raises(StaleMove) as caught:
        undo(shown, undoer)  # would undo the other employee's move

    assert "changed" in str(caught.value).lower()
    assert everything() == newer
    assert row(application)["stage_changed_by_id"] == other.pk


def test_stale_undo_after_another_employee_already_undid_it(
    recruiter, undoer, other, make
):
    check_api()
    application = make(S.APPLIED)
    application.move_to(
        S.SCREENING,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    shown = fresh(application)

    undo(fresh(application), other)  # back to Applied
    after_other_undo = everything()
    with pytest.raises(StaleMove):
        undo(shown, undoer)
    assert everything() == after_other_undo

    # The stage returns to Screening (eligible again), but this is a newer
    # change: the old button's token no longer matches.
    other_view = fresh(application)
    other_view.move_to(
        S.SCREENING,
        other,
        expected_stage=S.APPLIED,
        expected_changed_at=other_view.stage_changed_at,
    )
    assert row(application)["stage"] == shown.stage
    newer = everything()
    with pytest.raises(StaleMove):
        undo(shown, undoer)
    assert everything() == newer
    assert row(application)["stage_changed_by_id"] == other.pk


@pytest.mark.parametrize("mismatch", ["stage", "changed_at"])
def test_both_expected_values_must_match(undoer, make, mismatch):
    check_api()
    application = make(S.OFFER, S.APPLIED)
    before = everything()
    expected_stage = S.FINAL_REVIEW if mismatch == "stage" else application.stage
    expected_changed_at = application.stage_changed_at
    if mismatch == "changed_at":
        expected_changed_at += datetime.timedelta(microseconds=1)

    with pytest.raises(StaleMove):
        application.undo(
            undoer,
            expected_stage=expected_stage,
            expected_changed_at=expected_changed_at,
        )

    assert everything() == before


def test_stale_takes_precedence_over_ineligible(undoer, make):
    """Hired can't be undone, but a token from before the hire is stale first."""
    check_api()
    application = make(S.HIRED, S.OFFER)
    before = everything()

    with pytest.raises(StaleMove):
        application.undo(
            undoer,
            expected_stage=S.OFFER,
            expected_changed_at=application.stage_changed_at,
        )

    assert everything() == before


def test_two_undos_of_the_same_button_cannot_both_succeed(
    recruiter, undoer, other, make
):
    check_api()
    application = make(S.APPLIED)
    application.move_to(
        S.REJECTED,
        recruiter,
        expected_stage=S.APPLIED,
        expected_changed_at=application.stage_changed_at,
    )
    pages = [fresh(application), fresh(application)]

    outcomes = []
    for page, who in zip(pages, (undoer, other), strict=True):
        try:
            undo(page, who)
            outcomes.append("undone")
        except StaleMove:
            outcomes.append("stale")

    assert outcomes == ["undone", "stale"]
    final = row(application)
    assert (final["stage"], final["previous_stage"]) == (S.APPLIED, None)
    assert final["stage_changed_by_id"] == undoer.pk


def test_undo_is_one_conditional_update(recruiter, undoer, make):
    """Stage, token, and previous stage are all checked inside the UPDATE."""
    check_api()
    application = make(S.SCREENING, S.APPLIED)

    with CaptureQueriesContext(connection) as queries:
        undo(application, undoer)

    writes = [
        q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("UPDATE")
    ]
    assert len(writes) == 1, writes
    where = writes[0].upper().split(" WHERE ", 1)[1]
    for column in ('"STAGE"', '"STAGE_CHANGED_AT"', '"PREVIOUS_STAGE"'):
        assert column in where, (column, writes[0])
    assert not [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "DELETE"))
    ]
