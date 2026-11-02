from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CandidateForm
from .models import Candidate


class CandidateListView(ListView):
    """Active candidates by default; archived ones with ``?archived=1``."""

    model = Candidate  # ordered by Candidate.Meta.ordering: last name, first name, pk

    def showing_archived(self):
        return self.request.GET.get("archived") == "1"

    def get_queryset(self):
        return super().get_queryset().filter(is_archived=self.showing_archived())

    def get_context_data(self, **kwargs):
        kwargs["showing_archived"] = self.showing_archived()
        return super().get_context_data(**kwargs)


class CandidateCreateView(CreateView):
    model = Candidate
    form_class = CandidateForm


class CandidateDetailView(DetailView):
    model = Candidate

    def get_context_data(self, **kwargs):
        # Through the reverse relation only: candidates never imports hiring.
        kwargs["applications"] = self.object.applications.select_related("opening")
        return super().get_context_data(**kwargs)


class CandidateUpdateView(UpdateView):
    model = Candidate
    form_class = CandidateForm


@require_http_methods(["GET", "POST"])
def delete_candidate(request, pk):
    """GET -> read-only confirmation; POST -> permanently delete the candidate.

    A candidate with applications is protected (PROTECT foreign key): nothing is
    deleted and the employee is told why. This catches Django's generic
    ProtectedError, so candidates never imports hiring.
    """
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "GET":
        template = (
            "candidates/_confirm_delete_modal.html"
            if request.headers.get("HX-Request")
            else "candidates/confirm_delete_page.html"
        )
        return render(request, template, {"candidate": candidate})
    name = str(candidate)
    try:
        candidate.delete()
    except ProtectedError:
        messages.error(request, f"{name} has applications, so they can't be deleted.")
        return redirect(candidate)
    messages.success(request, f"Deleted candidate {name}.")
    return redirect("candidates:list")


def _blocking_text(applications):
    return ", ".join(f"{a.opening} ({a.get_stage_display()})" for a in applications)


@require_http_methods(["GET", "POST"])
def archive_candidate(request, pk):
    """GET -> read-only confirmation listing any blocking applications;
    POST -> archive through Candidate.archive(), which re-checks eligibility."""
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "GET":
        template = (
            "candidates/_confirm_archive_modal.html"
            if request.headers.get("HX-Request")
            else "candidates/confirm_archive_page.html"
        )
        blocking = candidate.applications.active().select_related("opening")
        return render(request, template, {"candidate": candidate, "blocking": blocking})
    if candidate.is_archived:
        messages.info(request, f"{candidate} is already archived.")
        return redirect(candidate)
    blocking = candidate.archive()
    if blocking:
        messages.error(
            request,
            f"{candidate} can't be archived while they have active applications: "
            f"{_blocking_text(blocking)}. Resolve these first.",
        )
    else:
        messages.success(
            request,
            f"Archived {candidate}. They're hidden from the active candidate list.",
        )
    return redirect(candidate)


@require_POST
def unarchive_candidate(request, pk):
    """POST only: a separate, deliberate action that restores the candidate."""
    candidate = get_object_or_404(Candidate, pk=pk)
    if candidate.unarchive():
        messages.success(
            request, f"Unarchived {candidate}. They're back in the active list."
        )
    else:
        messages.info(request, f"{candidate} isn't archived.")
    return redirect(candidate)
