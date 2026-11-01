from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import Lower
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import JobOpeningForm, SkillForm
from .models import JobOpening, Skill


class JobOpeningListView(ListView):
    # Ordered by JobOpening.Meta.ordering: title, department, pk.
    queryset = JobOpening.objects.prefetch_related("skills")
    context_object_name = "openings"


class JobOpeningCreateView(CreateView):
    model = JobOpening
    form_class = JobOpeningForm  # no status field: new openings start Open


class JobOpeningDetailView(DetailView):
    model = JobOpening
    context_object_name = "opening"


class JobOpeningUpdateView(UpdateView):
    model = JobOpening
    form_class = JobOpeningForm
    context_object_name = "opening"


class SkillListView(ListView):
    # Every opening using a skill is counted, Open and Closed alike. The ordering
    # is explicit because Django does not apply Meta.ordering to this aggregate
    # (GROUP BY) query; it matches Skill.Meta.ordering: A-Z ignoring case, then pk.
    queryset = Skill.objects.annotate(opening_count=Count("openings")).order_by(
        Lower("name"), "pk"
    )
    context_object_name = "skills"


class SkillDeleteView(DeleteView):
    """GET shows a confirmation page and changes nothing; only a POST deletes.

    Deleting a Skill removes its rows in the opening-skill link table; the
    JobOpening rows themselves are never deleted or saved.
    """

    # Count every opening using the skill, Open and Closed alike.
    queryset = Skill.objects.annotate(opening_count=Count("openings"))
    context_object_name = "skill"
    success_url = reverse_lazy("openings:skill_list")

    def form_valid(self, form):
        # Capture what is being deleted before the row is gone.
        name = self.object.name
        count = self.object.opening_count
        response = super().form_valid(form)
        noun = "opening" if count == 1 else "openings"
        messages.success(
            self.request, f'Deleted skill "{name}" (removed from {count} {noun}).'
        )
        return response


@require_POST
def add_skill_inline(request):
    """HTMX: create one Skill and return the re-rendered skills checklist.

    Works only with Skill records. It never loads, creates, or saves a JobOpening,
    so the rest of the unsaved opening form is left untouched in the browser.
    """
    skill_form = SkillForm(data={"name": request.POST.get("new_skill_name", "")})

    # Keep the employee's current ticks, but only for real, existing skills.
    posted_ids = [v for v in request.POST.getlist("skills") if v.isdigit()]
    selected = list(
        Skill.objects.filter(pk__in=posted_ids).values_list("pk", flat=True)
    )

    if skill_form.is_valid():
        selected.append(skill_form.save().pk)
        skill_form = SkillForm()  # clear the input after a successful add

    skills_field = JobOpeningForm(initial={"skills": selected})["skills"]
    return render(
        request,
        "openings/_skills_field.html",
        {"field": skills_field, "skill_form": skill_form},
    )
