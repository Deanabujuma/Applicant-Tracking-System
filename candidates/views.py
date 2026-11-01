from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CandidateForm
from .models import Candidate


class CandidateListView(ListView):
    model = Candidate  # ordered by Candidate.Meta.ordering: last name, first name, pk


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
