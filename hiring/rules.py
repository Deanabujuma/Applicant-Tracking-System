"""The stage-transition rules. Pure Python: no Django, models, or database.

Works on stage values (the strings stored in ``Application.stage``); a
``Stage`` member works too, since it is a ``str``. This is the one place the
movement policy lives. ``Application.move_to()`` and the workspace ask it
what is allowed, so the views and templates never decide on their own.
"""

# The eight stages in pipeline order, matching ``hiring.models.Stage``.
LABELS = {
    "applied": "Applied",
    "screening": "Screening",
    "interview": "Interview",
    "final_review": "Final Review",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}
STAGES = tuple(LABELS)
ACTIVE = STAGES[:5]  # Applied through Offer
HIRED = "hired"
ENDINGS = ("rejected", "withdrawn")


def why_not(from_stage, to_stage):
    """None if the move is allowed, otherwise a plain-language reason."""
    from_stage, to_stage = str(from_stage), str(to_stage)
    if from_stage == to_stage:
        return f"It's already in {LABELS[from_stage]}."
    if from_stage == HIRED:
        return "Hired is permanent. This application can't be changed."
    if from_stage in ENDINGS:
        return (
            f"This application is {LABELS[from_stage]}. "
            "The only way out is Undo, if it's still available."
        )
    if to_stage == HIRED:
        return (
            None if from_stage == "offer" else "Hired can only be reached from Offer."
        )
    if to_stage in ENDINGS:
        return None
    if ACTIVE.index(to_stage) < ACTIVE.index(from_stage):
        return "Moving backward isn't a normal move. Use Undo to correct the last move."
    return None


def allowed_moves(stage):
    """Every stage this one may move to, in pipeline order."""
    return tuple(to for to in STAGES if why_not(stage, to) is None)


def kind_of(from_stage, to_stage):
    """'advance', 'skip', 'end', or 'hire' for an allowed move."""
    if why_not(from_stage, to_stage) is not None:
        raise ValueError(f"{from_stage} → {to_stage} is not an allowed move.")
    from_stage, to_stage = str(from_stage), str(to_stage)
    if to_stage == HIRED:
        return "hire"
    if to_stage in ENDINGS:
        return "end"
    steps = ACTIVE.index(to_stage) - ACTIVE.index(from_stage)
    return "advance" if steps == 1 else "skip"


def skipped_stages(from_stage, to_stage):
    """Labels of the active stages a forward move jumps over, in order."""
    from_stage, to_stage = str(from_stage), str(to_stage)
    if from_stage not in ACTIVE or to_stage not in ACTIVE:
        return []
    start, end = ACTIVE.index(from_stage), ACTIVE.index(to_stage)
    return [LABELS[stage] for stage in ACTIVE[start + 1 : end]]


def undo_blocker(stage, previous_stage):
    """None if Undo may return ``stage`` to ``previous_stage``; else why not.

    Undo reverses the latest recorded move, once. It is never available from
    Hired (permanent), nor without a previous stage (none yet, or already
    undone). The recorded move ``previous_stage -> stage`` must be one the
    move rules allow, so Undo can only go back where the application really
    came from, never to an impossible or corrupted stage.
    """
    stage = str(stage)
    if stage == HIRED:
        return "Hired is permanent — it can't be undone."
    if previous_stage is None:
        return "Nothing to undo. Undo only reverses the most recent move, once."
    previous_stage = str(previous_stage)
    if (
        stage not in LABELS
        or previous_stage not in LABELS
        or why_not(previous_stage, stage) is not None
    ):
        return "The recorded previous stage doesn't match a move to this stage, so it can't be undone."
    return None
