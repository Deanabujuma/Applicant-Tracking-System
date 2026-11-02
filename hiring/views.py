from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET, require_http_methods

from candidates.models import Candidate
from openings.models import JobOpening

from .forms import ApplicationForm
from .models import ACTIVE_STAGES, Application, Stage


@require_GET
def workspace(request):
    """The openings-first hiring workspace at ``/``. Read-only.

    ``?opening=all`` (the default) or ``?opening=<pk>`` picks the scope. The
    sidebar lists every opening with its active-applicant count (Applied
    through Offer only); the main area counts the scope's applications in all
    eight stages and lists them, one row per application. ``&application=<pk>``
    shows that application's read-only details; it must belong to the scope,
    or the response is a 404. HTMX navigation gets
    just the ``_workspace.html`` partial; everything else, including an htmx
    history restore, gets the full page.
    """
    openings = JobOpening.objects.annotate(
        active_count=Count(
            "applications", filter=Q(applications__stage__in=ACTIVE_STAGES)
        )
    ).order_by("title", "department", "pk")  # aggregates drop Meta.ordering

    selected = None
    choice = request.GET.get("opening", "all")
    if choice != "all":
        try:
            opening_id = int(choice)
        except ValueError:
            return HttpResponseBadRequest("Invalid opening.")
        selected = get_object_or_404(JobOpening, pk=opening_id)

    applications = Application.objects.all()
    if selected is not None:
        applications = applications.filter(opening=selected)
    per_stage = dict(
        applications.order_by().values_list("stage").annotate(n=Count("pk"))
    )
    stage_counts = [(stage, per_stage.get(stage.value, 0)) for stage in Stage]

    selected_application = None
    application_choice = request.GET.get("application")
    if application_choice is not None:
        try:
            application_id = int(application_choice)
        except ValueError:
            return HttpResponseBadRequest("Invalid application.")
        # Scoped lookup: another opening's application is a 404 here.
        selected_application = get_object_or_404(
            applications.select_related("candidate", "opening"), pk=application_id
        )

    context = {
        "openings": openings,
        "selected": selected,
        "scope": selected.pk if selected is not None else "all",
        "selected_application": selected_application,
        "stage_counts": stage_counts,
        "total": sum(per_stage.values()),
        "applications": applications.select_related("candidate", "opening").order_by(
            "candidate__last_name", "candidate__first_name", "pk"
        ),
    }
    partial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    template = "hiring/_workspace.html" if partial else "hiring/workspace.html"
    response = render(request, template, context)
    patch_vary_headers(response, ("HX-Request", "HX-History-Restore-Request"))
    return response


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
