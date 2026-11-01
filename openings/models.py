from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

DUPLICATE_SKILL_MESSAGE = "A skill with this name already exists."


class OpeningStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Skill(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = (Lower("name"), "pk")
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                name="skill_name_ci_unique",
                violation_error_message=DUPLICATE_SKILL_MESSAGE,
            ),
        )

    def __str__(self):
        return self.name


class JobOpening(models.Model):
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=10, choices=OpeningStatus.choices, default=OpeningStatus.OPEN
    )
    skills = models.ManyToManyField(Skill, blank=True, related_name="openings")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", "department", "pk")

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def get_absolute_url(self):
        return reverse("openings:detail", kwargs={"pk": self.pk})

    def close(self):
        """Close the opening. Returns False (saving nothing) if already Closed."""
        return self._set_status(OpeningStatus.CLOSED)

    def reopen(self):
        """Reopen the opening. Returns False (saving nothing) if already Open."""
        return self._set_status(OpeningStatus.OPEN)

    def _set_status(self, status):
        if self.status == status:
            return False
        self.status = status
        # Write only these columns so no other field can change.
        self.save(update_fields=["status", "updated_at"])
        return True
