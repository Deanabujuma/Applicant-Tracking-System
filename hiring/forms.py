from django import forms
from django.db import IntegrityError, transaction
from django.utils import timezone

from candidates.models import Candidate
from openings.models import JobOpening, OpeningStatus

from .models import DUPLICATE_APPLICATION_MESSAGE, Application


def _opening_label(opening):
    return f"{opening} ({opening.department})"


def _candidate_label(candidate):
    return f"{candidate} ({candidate.email})"


class ApplicationForm(forms.Form):
    """The one application form, used from a candidate's page and an opening's.

    Exactly one side (candidate or opening) is fixed by the caller from the URL;
    the form has a single field for the other side. The stage and its metadata
    are never form fields: ``save()`` sets them. ``clean()`` checks the whole
    pair, so the rules hold for both entry points and for forged submissions.
    """

    def __init__(self, *args, candidate=None, opening=None, **kwargs):
        if (candidate is None) == (opening is None):
            msg = "Pass exactly one of candidate or opening."
            raise ValueError(msg)
        super().__init__(*args, **kwargs)
        self.candidate = candidate
        self.opening = opening

        # Validate against every record, so an ineligible choice gets a clear
        # message from clean() instead of a generic "invalid choice"...
        if candidate is not None:
            self.chosen = "opening"
            field = forms.ModelChoiceField(queryset=JobOpening.objects.all())
            eligible = JobOpening.objects.filter(status=OpeningStatus.OPEN).exclude(
                applications__candidate=candidate
            )
            label = _opening_label
        else:
            self.chosen = "candidate"
            field = forms.ModelChoiceField(queryset=Candidate.objects.all())
            eligible = Candidate.objects.filter(is_archived=False).exclude(
                applications__opening=opening
            )
            label = _candidate_label

        # ...but offer only eligible choices (none if the fixed side can't apply).
        if self.fixed_problem():
            eligible = eligible.none()
        field.widget.choices = [("", "---------")] + [
            (obj.pk, label(obj)) for obj in eligible
        ]
        self.fields[self.chosen] = field

    def fixed_problem(self):
        """Why the URL's fixed record can't take new applications, or None."""
        if self.candidate is not None and self.candidate.is_archived:
            return f"{self.candidate} is archived and can't receive new applications."
        if self.opening is not None and self.opening.status != OpeningStatus.OPEN:
            return f"Opening {self.opening} is Closed and isn't accepting applications."
        return None

    def clean(self):
        cleaned = super().clean()
        if self.chosen not in cleaned:
            return cleaned  # the field already has its own error
        candidate = self.candidate or cleaned["candidate"]
        opening = self.opening or cleaned["opening"]
        if candidate.is_archived:
            self.add_error(
                None, f"{candidate} is archived and can't receive new applications."
            )
        if opening.status != OpeningStatus.OPEN:
            self.add_error(
                None, f"Opening {opening} is Closed and isn't accepting applications."
            )
        if Application.objects.filter(candidate=candidate, opening=opening).exists():
            self.add_error(None, DUPLICATE_APPLICATION_MESSAGE)
        self.pair = (candidate, opening)
        return cleaned

    def save(self, employee):
        """Create the application in Applied; the application sets its metadata.

        Returns None (with a form error) if the database's unique constraint
        rejects a duplicate that slipped past ``clean()``.
        """
        candidate, opening = self.pair
        try:
            with transaction.atomic():
                return Application.objects.create(
                    candidate=candidate,
                    opening=opening,
                    stage_changed_by=employee,
                    stage_changed_at=timezone.now(),
                )
        except IntegrityError:
            self.add_error(None, DUPLICATE_APPLICATION_MESSAGE)
            return None
