from django import forms

from .models import DUPLICATE_EMAIL_MESSAGE, Candidate


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "source",
            "source_detail",
            "notes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set by clean_email() so the template can link to the existing record.
        self.duplicate_candidate = None

    def clean_email(self):
        """Reject an email already used by another candidate, ignoring capitalization.

        Mirrors the database's Lower("email") unique constraint, which stays as the
        final safeguard. The candidate being edited is excluded so it can be re-saved.
        """
        email = self.cleaned_data["email"]
        others = Candidate.objects.filter(email__iexact=email)
        if self.instance.pk is not None:
            others = others.exclude(pk=self.instance.pk)
        self.duplicate_candidate = others.first()
        if self.duplicate_candidate is not None:
            raise forms.ValidationError(DUPLICATE_EMAIL_MESSAGE, code="duplicate_email")
        return email
