from django.conf import settings
from django.db import models
from django.utils import timezone

from . import rules

DUPLICATE_APPLICATION_MESSAGE = "This candidate has already applied to this opening."


class Stage(models.TextChoices):
    """Hiring stages. Applied through Offer are active; the rest are closed."""

    APPLIED = "applied", "Applied"
    SCREENING = "screening", "Screening"
    INTERVIEW = "interview", "Interview"
    FINAL_REVIEW = "final_review", "Final Review"
    OFFER = "offer", "Offer"
    HIRED = "hired", "Hired"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


# "Active" (not yet closed) stages, Applied through Offer, as defined by the rules.
ACTIVE_STAGES = tuple(Stage(value) for value in rules.ACTIVE)


class InvalidMove(Exception):
    """A stage change the rules don't allow. The message says why."""


class StaleMove(InvalidMove):
    """The application's stage changed after the move was requested."""


class ApplicationQuerySet(models.QuerySet):
    def active(self):
        """Applications still in progress: Applied through Offer.

        Hired, Rejected, and Withdrawn are closed. Read-only; it never changes
        any record. Also available through the reverse relations, e.g.
        ``candidate.applications.active()``, so other apps needn't import hiring.
        """
        return self.filter(stage__in=ACTIVE_STAGES)


class Application(models.Model):
    """One candidate applying to one opening.

    Stage metadata (previous stage, who and when it last changed) is stored
    from the start so the later move and Undo phases need no new migration.
    None of these fields are editable by employees; the application sets them.
    """

    # String references keep the dependency one-way: candidates and openings
    # never import hiring.
    # PROTECT: a candidate or opening with any application can't be deleted,
    # even directly through the model or a queryset (ProtectedError).
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    opening = models.ForeignKey(
        "openings.JobOpening",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    stage = models.CharField(
        max_length=20, choices=Stage.choices, default=Stage.APPLIED, editable=False
    )
    # None means "no previous stage" (nothing to undo).
    previous_stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        null=True,
        blank=True,
        default=None,
        editable=False,
    )
    # Accounts are deactivated, never deleted, so keep who made each change.
    stage_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stage_changes",
        editable=False,
    )
    stage_changed_at = models.DateTimeField(default=timezone.now, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("candidate", "opening"),
                name="application_unique_candidate_opening",
                violation_error_message=DUPLICATE_APPLICATION_MESSAGE,
            ),
        )

    def __str__(self):
        return f"{self.candidate} → {self.opening}"

    def move_to(self, to_stage, employee, expected_stage, expected_changed_at):
        """Move to ``to_stage`` as ``employee``, if nothing changed since.

        The only normal way a stage changes. ``expected_stage`` and
        ``expected_changed_at`` are the stage and ``stage_changed_at`` the
        employee saw; every move and Undo updates that timestamp, so together
        they identify the exact state (a stage that was changed and changed
        back still counts as changed). The move must be allowed by
        ``hiring.rules`` from ``expected_stage``, and it is saved with one
        conditional UPDATE (``WHERE pk = … AND stage = … AND stage_changed_at =
        …``), so the checks and the write happen together: of two employees
        confirming from the same state, only one can succeed. Records the stage
        left as ``previous_stage``, plus who and when.

        Raises ``StaleMove`` if the stored stage or timestamp no longer matches
        (checked first), otherwise ``InvalidMove`` with the rules' reason.
        Neither changes anything.
        """
        to_stage, expected_stage = str(to_stage), str(expected_stage)
        if {to_stage, expected_stage} <= set(rules.STAGES):
            reason = rules.why_not(expected_stage, to_stage)
        else:
            reason = "That isn't a hiring stage."

        if reason is None:
            now = timezone.now()
            changes = {
                "stage": to_stage,
                "previous_stage": expected_stage,
                "stage_changed_by": employee,
                "stage_changed_at": now,
                "updated_at": now,  # update() skips auto_now
            }
            saved = Application.objects.filter(
                pk=self.pk,
                stage=expected_stage,
                stage_changed_at=expected_changed_at,
            ).update(**changes)
            if saved:
                for name, value in changes.items():
                    setattr(self, name, value)
                return

        # Not saved: stale if anything changed, otherwise the rules said no.
        current, changed_at = Application.objects.values_list(
            "stage", "stage_changed_at"
        ).get(pk=self.pk)
        if current != expected_stage:
            raise StaleMove(
                f"This application changed to {Stage(current).label} after you "
                "opened this. Nothing was changed."
            )
        if changed_at != expected_changed_at:
            raise StaleMove(
                "This application was changed by someone else after you opened "
                f"this (it's in {Stage(current).label} again). Nothing was changed."
            )
        raise InvalidMove(reason)

    def undo(self, employee, expected_stage, expected_changed_at):
        """Undo the latest move as ``employee``, if nothing changed since.

        ``expected_stage`` and ``expected_changed_at`` are the stage and
        ``stage_changed_at`` shown with the Undo button. Every move and Undo
        updates ``stage_changed_at``, so together they identify that exact
        state: if either differs from the stored row, another employee moved
        or undid the application, and ``StaleMove`` is raised (checked first).
        Otherwise ``hiring.rules.undo_blocker`` decides, using the stored
        history, and a refusal raises ``InvalidMove`` with its reason.

        Undo returns to the stored ``previous_stage`` and clears it, so it is
        single-use until a new move. It is saved with one conditional UPDATE
        matching the ID, expected stage, expected timestamp, and the stored
        previous stage, so the checks and the write happen together. Nothing
        changes when it raises.
        """
        stale = StaleMove(
            "This application changed after this page loaded. Nothing was undone."
        )
        expected_stage = str(expected_stage)
        stored = Application.objects.values(
            "stage", "previous_stage", "stage_changed_at"
        ).get(pk=self.pk)
        if (
            stored["stage"] != expected_stage
            or stored["stage_changed_at"] != expected_changed_at
        ):
            raise stale
        reason = rules.undo_blocker(stored["stage"], stored["previous_stage"])
        if reason is not None:
            raise InvalidMove(reason)

        now = timezone.now()
        changes = {
            "stage": stored["previous_stage"],
            "previous_stage": None,
            "stage_changed_by": employee,
            "stage_changed_at": now,
            "updated_at": now,  # update() skips auto_now
        }
        saved = Application.objects.filter(
            pk=self.pk,
            stage=expected_stage,
            stage_changed_at=expected_changed_at,
            previous_stage=stored["previous_stage"],  # non-null: eligible above
        ).update(**changes)
        if not saved:  # changed between the read and the write
            raise stale
        for name, value in changes.items():
            setattr(self, name, value)
