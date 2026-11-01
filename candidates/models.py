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
