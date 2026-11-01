from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from candidates.models import Candidate
from openings.models import JobOpening

from .forms import ApplicationForm


def workspace(request):
    """Placeholder hiring workspace. Phase 7 replaces this with the real workspace."""
    return render(request, "hiring/workspace.html")


@require_http_methods(["GET", "POST"])
def application_create(request):
    """The shared Add Application page: ``?candidate=<pk>`` or ``?opening=<pk>``.

    The fixed side comes only from the URL (anything posted for it is ignored),
    and the form validates the whole pair on every POST.
    """
    given = {
        key: request.GET[key] for key in ("candidate", "opening") if key in request.GET
    }
    if len(given) != 1:
        return HttpResponseBadRequest("Give exactly one of ?candidate= or ?opening=.")
    [(side, pk)] = given.items()
    if not pk.isdigit():
        return HttpResponseBadRequest(f"?{side}= must be a record ID.")
    model = Candidate if side == "candidate" else JobOpening
    fixed = get_object_or_404(model, pk=pk)

    form = ApplicationForm(request.POST or None, **{side: fixed})
    if request.method == "POST" and form.is_valid():
        application = form.save(request.user)
        if application is not None:
            messages.success(
                request,
                f"Added application: {application.candidate} → "
                f"{application.opening}. It starts in Applied.",
            )
            return redirect(fixed)

    return render(
        request,
        "hiring/application_form.html",
        {"form": form, "fixed": fixed, "side": side},
    )
