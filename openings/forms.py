from django import forms

from .models import DUPLICATE_SKILL_MESSAGE, JobOpening, Skill


class JobOpeningForm(forms.ModelForm):
    """Opening details and skills. Status is deliberately absent: it changes only
    through the confirmed close/reopen actions (Phase 4)."""

    # Any existing skill is a valid choice, but the widget submits only this
    # opening's (pending) skills as hidden inputs; the catalog is never rendered.
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.all(),
        widget=forms.MultipleHiddenInput,
        required=False,
    )

    class Meta:
        model = JobOpening
        fields = ("title", "department", "location", "description", "skills")

    def assigned_skills(self):
        """The Skills this form currently holds, for display.

        Reads the bound data (pending changes, or a re-shown invalid form) or,
        when unbound, the opening's saved skills. Unknown or junk IDs are skipped.
        """
        ids = [str(value) for value in self["skills"].value() or ()]
        return Skill.objects.filter(pk__in=[i for i in ids if i.isdigit()])

    def skill_suggestions(self):
        """Every skill name, for the Add Skill datalist. Suggestions only."""
        return Skill.objects.values_list("name", flat=True)


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
