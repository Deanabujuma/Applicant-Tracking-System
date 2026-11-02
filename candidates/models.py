from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

DUPLICATE_EMAIL_MESSAGE = "A candidate with this email already exists."


class Source(models.TextChoices):
    JOB_BOARD = "job_board", "Job Board"
    REFERRAL = "referral", "Referral"
    COMPANY_WEBSITE = "company_website", "Company Website"
    OTHER = "other", "Other"


class Candidate(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    source_detail = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "pk")
        constraints = (
            models.UniqueConstraint(
                Lower("email"),
                name="candidate_email_ci_unique",
                violation_error_message=DUPLICATE_EMAIL_MESSAGE,
            ),
        )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse("candidates:detail", kwargs={"pk": self.pk})

    def archive(self):
        """Archive this candidate unless they have active applications.

        Returns the blocking active applications (with their openings): a
        non-empty list means archiving was refused and nothing changed; an empty
        list means the candidate is archived. Application stages are never
        changed. "Active" comes from hiring's ``active()`` through the reverse
        relation, so candidates never imports hiring.
        """
        blocking = list(self.applications.active().select_related("opening"))
        if blocking or self.is_archived:
            return blocking  # refused, or already archived: nothing to save
        self.is_archived = True
        self.save(update_fields=["is_archived", "updated_at"])
        return []

    def unarchive(self):
        """Return an archived candidate to active use. Returns False (saving
        nothing) if they weren't archived."""
        if not self.is_archived:
            return False
        self.is_archived = False
        self.save(update_fields=["is_archived", "updated_at"])
        return True
