from django.conf import settings
from django.db import models
from django.utils import timezone

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


# The one definition of an "active" (not yet closed) stage.
ACTIVE_STAGES = (
    Stage.APPLIED,
    Stage.SCREENING,
    Stage.INTERVIEW,
    Stage.FINAL_REVIEW,
    Stage.OFFER,
)


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
