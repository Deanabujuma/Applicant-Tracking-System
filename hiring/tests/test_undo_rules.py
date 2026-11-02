"""Phase 9 Test 1: ``undo_blocker(stage, previous_stage)`` in ``hiring/rules.py``."""

import itertools

import pytest

from hiring import rules
from hiring.models import Stage
from hiring.tests.test_rules import ALLOWED

S = Stage
PREVIOUS = [None, *Stage]  # no previous stage, or any of the eight
CASES = list(itertools.product(Stage, PREVIOUS))  # 8 x 9 = 72


def case_id(value):
    return "none" if value is None else value.value


def undo_blocker():
    """The function; a missing one is an assertion failure, not a crash."""
    blocker = getattr(rules, "undo_blocker", None)
    assert callable(blocker), "no rules.undo_blocker"
    return blocker


def expected_allowed(stage, previous):
    """Undo is allowed only if it reverses a move the rules could have made:
    previous -> stage. Never from Hired, never without a previous stage."""
    if stage == S.HIRED or previous is None:
        return False
    return stage in ALLOWED[previous]


@pytest.mark.parametrize(("stage", "previous"), CASES, ids=case_id)
def test_undo_blocker_for_every_stage_and_previous_stage(stage, previous):
    blocker = undo_blocker()

    reason = blocker(stage, previous)

    if expected_allowed(stage, previous):
        assert reason is None
    else:
        assert isinstance(reason, str)
        assert reason.strip()
        if stage == S.HIRED:  # even with a previous stage (Offer)
            assert "permanent" in reason.lower()
            assert "hired" in reason.lower()
        elif previous is None:
            assert "nothing to undo" in reason.lower()


@pytest.mark.parametrize(
    ("stage", "previous"),
    [
        # Active stages, after a one-step move or a skip.
        (S.SCREENING, S.APPLIED),
        (S.OFFER, S.APPLIED),
        (S.FINAL_REVIEW, S.INTERVIEW),
        # Ending stages, from wherever they were entered.
        (S.REJECTED, S.APPLIED),
        (S.REJECTED, S.OFFER),
        (S.WITHDRAWN, S.SCREENING),
        (S.WITHDRAWN, S.FINAL_REVIEW),
    ],
    ids=case_id,
)
def test_undo_is_available_after_an_eligible_move(stage, previous):
    assert undo_blocker()(stage, previous) is None
    assert undo_blocker()(stage.value, previous.value) is None  # plain values


@pytest.mark.parametrize("previous", PREVIOUS, ids=case_id)
def test_hired_is_never_undoable(previous):
    reason = undo_blocker()(S.HIRED, previous)
    assert reason is not None
    assert "permanent" in reason.lower()


@pytest.mark.parametrize("stage", list(Stage), ids=lambda s: s.value)
def test_no_previous_stage_means_nothing_to_undo(stage):
    reason = undo_blocker()(stage, None)
    assert reason is not None
    if stage != S.HIRED:
        assert "nothing to undo" in reason.lower()


def test_undo_never_widens_the_ordinary_move_rules():
    blocker = undo_blocker()
    moves_before = {stage: rules.allowed_moves(stage) for stage in Stage}
    reasons_before = {(a, b): rules.why_not(a, b) for a in Stage for b in Stage}
    kinds_before = {
        (a, b): rules.kind_of(a, b) for a in Stage for b in rules.allowed_moves(a)
    }
    skipped_before = {(a, b): rules.skipped_stages(a, b) for a in Stage for b in Stage}

    for stage, previous in CASES:
        if blocker(stage, previous) is None:
            # Undo goes backward; that is never an ordinary move.
            assert previous not in rules.allowed_moves(stage)
            assert rules.why_not(stage, previous) is not None

    # Asking about Undo changes none of the move rules.
    assert {stage: rules.allowed_moves(stage) for stage in Stage} == moves_before
    assert {(a, b): rules.why_not(a, b) for a in Stage for b in Stage} == reasons_before
    assert {
        (a, b): rules.kind_of(a, b) for a in Stage for b in rules.allowed_moves(a)
    } == kinds_before
    assert {
        (a, b): rules.skipped_stages(a, b) for a in Stage for b in Stage
    } == skipped_before


@pytest.mark.django_db
def test_undo_blocker_runs_no_queries(django_assert_num_queries):
    blocker = undo_blocker()
    with django_assert_num_queries(0):
        for stage, previous in CASES:
            blocker(stage, previous)
