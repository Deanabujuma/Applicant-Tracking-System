from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import (
    CreateView,
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


@require_POST
def add_skill_inline(request):
    """HTMX: add a skill, by name, to the opening form's pending skills.

    An existing name (any capitalization) reuses that shared Skill; a new name
    creates one. The skill is only added to the returned fragment's hidden
    inputs. This never loads, creates, or saves a JobOpening or its skill links,
    so nothing is assigned until the opening form is saved, and the rest of the
    unsaved form is left untouched in the browser.
    """
    name = request.POST.get("new_skill_name", "")
    skill_form = SkillForm(data={"name": name})
    notice = ""
    selected = _pending_skill_ids(request)

    existing = Skill.objects.filter(name__iexact=name.strip()).first()
    if existing is not None:
        if existing.pk in selected:
            notice = f"{existing.name} is already on this opening."
        else:
            selected.append(existing.pk)
        skill_form = SkillForm()  # clear the input
    elif skill_form.is_valid():  # a new name: blank/length validation still apply
        selected.append(skill_form.save().pk)
        skill_form = SkillForm()

    return _skills_fragment(request, selected, skill_form, notice)


@require_POST
def remove_skill_inline(request):
    """HTMX: drop one skill from the opening form's pending skills.

    Only the returned fragment changes. No Skill is deleted, and no JobOpening
    or skill link is loaded or saved, so Save stays the only step that changes an
    opening's skills, and Cancel discards the removal. An ID that isn't among the
    pending skills (forged, nonexistent, or junk) removes nothing.
    """
    remove_id = request.POST.get("remove_skill", "")
    selected = [pk for pk in _pending_skill_ids(request) if str(pk) != remove_id]
    return _skills_fragment(request, selected, SkillForm())


def _pending_skill_ids(request):
    """The posted pending skill IDs, keeping only real, existing skills."""
    posted_ids = [v for v in request.POST.getlist("skills") if v.isdigit()]
    return list(Skill.objects.filter(pk__in=posted_ids).values_list("pk", flat=True))


def _skills_fragment(request, selected, skill_form, notice=""):
    """Re-render the opening form's skills section for the given pending IDs."""
    skills_field = JobOpeningForm(initial={"skills": selected})["skills"]
    return render(
        request,
        "openings/_skills_field.html",
        {"field": skills_field, "skill_form": skill_form, "skill_notice": notice},
    )


def _confirmation(request, opening, action):
    """GET only: render the confirmation for ``action``. Never changes data.

    HTMX requests get just the modal fragment (swapped into #modal); ordinary
    GETs get a full page containing the same confirmation.
    """
    template = (
        "openings/_confirm_modal.html"
        if request.headers.get("HX-Request")
        else "openings/confirm_page.html"
    )
    return render(request, template, {"opening": opening, "action": action})


def _change_status(request, opening, method_name, done_text, already_text):
    changed = getattr(opening, method_name)()
    if changed:
        messages.success(request, done_text.format(opening=opening))
    else:
        messages.info(request, already_text.format(opening=opening))
    return redirect(opening)


@require_http_methods(["GET", "POST"])
def close_opening(request, pk):
    """GET: confirmation. POST: confirmed close, one-way (never reopens)."""
    opening = get_object_or_404(JobOpening, pk=pk)
    if request.method == "GET":
        return _confirmation(request, opening, "close")
    return _change_status(
        request,
        opening,
        "close",
        "Closed opening {opening}. It no longer accepts new applications.",
        "Opening {opening} is already closed.",
    )


@require_http_methods(["GET", "POST"])
def reopen_opening(request, pk):
    """GET: confirmation. POST: confirmed reopen, one-way (never closes)."""
    opening = get_object_or_404(JobOpening, pk=pk)
    if request.method == "GET":
        return _confirmation(request, opening, "reopen")
    return _change_status(
        request,
        opening,
        "reopen",
        "Reopened opening {opening}. It accepts new applications again.",
        "Opening {opening} is already open.",
    )


@require_http_methods(["GET", "POST"])
def delete_opening(request, pk):
    """GET -> confirmation (read-only); POST -> permanently delete the opening.

    Deleting removes only the opening and its skill links; Skills are kept.
    Phase 5 adds ProtectedError handling once applications can exist.
    """
    opening = get_object_or_404(JobOpening, pk=pk)
    if request.method == "GET":
        return _confirmation(request, opening, "delete")
    label = str(opening)  # "#N Title"; the pk is gone after delete()
    opening.delete()
    messages.success(request, f"Deleted opening {label}.")
    return redirect("openings:list")
