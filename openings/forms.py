from django import forms

from .models import DUPLICATE_SKILL_MESSAGE, JobOpening, Skill


class JobOpeningForm(forms.ModelForm):
    """Opening details and skills. Status is deliberately absent: it changes only
    through the confirmed close/reopen actions (Phase 4)."""

    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = JobOpening
        fields = ("title", "department", "location", "description", "skills")


class SkillForm(forms.ModelForm):
    """A single new skill. CharField strips surrounding whitespace; the model's
    Lower("name") constraint is validated before saving."""

    class Meta:
        model = Skill
        fields = ("name",)

    def clean_name(self):
        """Reject a name already used by another skill, ignoring capitalization.

        Mirrors the database's Lower("name") unique constraint, which stays as the
        final safeguard.
        """
        name = self.cleaned_data["name"]
        others = Skill.objects.filter(name__iexact=name)
        if self.instance.pk is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError(DUPLICATE_SKILL_MESSAGE, code="duplicate_skill")
        return name
