"""Phase 8 Test 1: the pure stage-transition rules in ``hiring/rules.py``."""

import ast
import importlib
import importlib.util
import itertools
from pathlib import Path

import pytest

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening

S = Stage

# The approved rules, written out in full rather than computed.
ALLOWED = {
    S.APPLIED: [
        S.SCREENING,
        S.INTERVIEW,
        S.FINAL_REVIEW,
        S.OFFER,
        S.REJECTED,
        S.WITHDRAWN,
    ],
    S.SCREENING: [S.INTERVIEW, S.FINAL_REVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN],
    S.INTERVIEW: [S.FINAL_REVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN],
    S.FINAL_REVIEW: [S.OFFER, S.REJECTED, S.WITHDRAWN],
    S.OFFER: [S.HIRED, S.REJECTED, S.WITHDRAWN],
    S.HIRED: [],
    S.REJECTED: [],
    S.WITHDRAWN: [],
}
ADVANCES = {
    (S.APPLIED, S.SCREENING),
    (S.SCREENING, S.INTERVIEW),
    (S.INTERVIEW, S.FINAL_REVIEW),
    (S.FINAL_REVIEW, S.OFFER),
}
ACTIVE = [S.APPLIED, S.SCREENING, S.INTERVIEW, S.FINAL_REVIEW, S.OFFER]
PAIRS = list(itertools.product(Stage, Stage))  # all 64


def expected_kind(from_stage, to_stage):
    if to_stage == S.HIRED:
        return "hire"
    if to_stage in (S.REJECTED, S.WITHDRAWN):
        return "end"
    return "advance" if (from_stage, to_stage) in ADVANCES else "skip"


def expected_reason_words(from_stage, to_stage):
    """Words a meaningful refusal reason must contain, by why it's refused."""
    if from_stage == to_stage:
        return ["already", from_stage.label]
    if from_stage == S.HIRED:
        return ["Hired", "permanent"]
    if from_stage in (S.REJECTED, S.WITHDRAWN):
        return [from_stage.label]
    if to_stage == S.HIRED:
        return ["Hired", "only", "Offer"]
    return ["backward"]


def load_rules():
    """The rules module; a missing module is an assertion failure, not a crash."""
    assert importlib.util.find_spec("hiring.rules") is not None, "no hiring/rules.py"
    return importlib.import_module("hiring.rules")


@pytest.mark.parametrize("stage", list(Stage), ids=lambda s: s.value)
def test_allowed_moves_lists_exactly_the_permitted_destinations(stage):
    rules = load_rules()
    moves = rules.allowed_moves(stage)

    assert [str(s) for s in moves] == [s.value for s in ALLOWED[stage]]
    assert rules.allowed_moves(stage.value) == moves  # plain values work too


@pytest.mark.parametrize(
    ("from_stage", "to_stage"), PAIRS, ids=[f"{a.value}-{b.value}" for a, b in PAIRS]
)
def test_every_pair_of_stages(from_stage, to_stage):
    rules = load_rules()
    allowed = to_stage in ALLOWED[from_stage]
    reason = rules.why_not(from_stage, to_stage)

    if allowed:
        assert reason is None
        assert rules.kind_of(from_stage, to_stage) == expected_kind(
            from_stage, to_stage
        )
    else:
        assert isinstance(reason, str)
        assert reason.strip()
        for word in expected_reason_words(from_stage, to_stage):
            assert word.lower() in reason.lower(), (word, reason)
        with pytest.raises(ValueError, match="not an allowed move"):
            rules.kind_of(from_stage, to_stage)

    # The three functions agree with each other.
    assert (to_stage in rules.allowed_moves(from_stage)) is allowed


def test_rules_summary_matches_the_approved_policy():
    """The headline rules, stated directly."""
    rules = load_rules()
    for i, from_stage in enumerate(ACTIVE):
        moves = rules.allowed_moves(from_stage)
        # Forward only (one step or a skip), never backward.
        assert all(s not in moves for s in ACTIVE[: i + 1])
        assert all(s in moves for s in ACTIVE[i + 1 :])
        # Ending is always possible from an active stage.
        assert S.REJECTED in moves
        assert S.WITHDRAWN in moves
        # Hired only from Offer.
        assert (S.HIRED in moves) is (from_stage == S.OFFER)
    for closed in (S.HIRED, S.REJECTED, S.WITHDRAWN):
        assert list(rules.allowed_moves(closed)) == []


def test_rules_module_is_pure():
    """No models, database, views, or templates: just stage values."""
    rules = load_rules()
    source = Path(rules.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    forbidden = (
        "django",
        "hiring",
        "candidates",
        "openings",
        ".models",
        ".views",
        ".forms",
    )
    assert not [m for m in imported if m.startswith(forbidden)], imported


@pytest.mark.django_db
def test_evaluating_rules_never_queries_or_changes_applications(
    django_user_model, django_assert_num_queries
):
    rules = load_rules()
    employee = django_user_model.objects.create_user(username="jsmith")
    opening = JobOpening.objects.create(title="Data Analyst", department="IT")
    for n, stage in enumerate(Stage):
        Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=f"P{n}",
                last_name="Doe",
                email=f"p{n}@example.com",
                source=Source.REFERRAL,
            ),
            opening=opening,
            stage=stage,
            stage_changed_by=employee,
        )
    before = list(Application.objects.order_by("pk").values())

    with django_assert_num_queries(0):
        for from_stage, to_stage in PAIRS:
            rules.allowed_moves(from_stage)
            if rules.why_not(from_stage, to_stage) is None:
                rules.kind_of(from_stage, to_stage)

    assert list(Application.objects.order_by("pk").values()) == before
