import datetime

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from candidates.models import Candidate
from openings.models import JobOpening

from . import rules
from .forms import ApplicationForm
from .models import ACTIVE_STAGES, Application, InvalidMove, Stage


class _BadParameter(Exception):
    """A malformed query or form value: the response is a 400."""


def _opening_for(choice):
    """The opening an ``opening`` value selects: None for "all" (the default)."""
    if choice in (None, "all"):
        return None
    try:
        opening_id = int(choice)
    except ValueError:
        raise _BadParameter("Invalid opening.") from None
    return get_object_or_404(JobOpening, pk=opening_id)


def _changed_at(value):
    """Parse a posted ``expected_changed_at`` (ISO 8601, with a time zone)."""
    if not value:
        raise _BadParameter("Give expected_changed_at.")
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise _BadParameter("Invalid expected_changed_at.") from None
    if parsed.tzinfo is None:
        raise _BadParameter("expected_changed_at needs a time zone.")
    return parsed


def _scoped_application(data, pk):
    """(selected opening, application) for a stage-change request.

    The application must be in the ``opening`` scope, or it's a 404.
    """
    selected = _opening_for(data.get("opening"))
    scoped = Application.objects.select_related("candidate", "opening")
    if selected is not None:
        scoped = scoped.filter(opening=selected)
    return selected, get_object_or_404(scoped, pk=pk)


def _stage_change_response(request, selected, application, level, text):
    """After a move or Undo: HTMX gets the refreshed workspace plus
    out-of-band updates clearing #modal and showing the one message; ordinary
    POSTs redirect back to the selection with a one-time message."""
    if request.headers.get("HX-Request"):
        context = _workspace_context(selected, application.pk)
        context["message"] = {
            "level": "success" if level == messages.SUCCESS else "error",
            "text": text,
        }
        return render(request, "hiring/_move_response.html", context)
    messages.add_message(request, level, text)
    return redirect(_selection_url(selected, application))


def _scope_value(selected):
    return selected.pk if selected is not None else "all"


def _selection_url(selected, application):
    """The workspace URL showing ``application`` within the scope."""
    return (
        f"{reverse('hiring:workspace')}?opening={_scope_value(selected)}"
        f"&application={application.pk}"
    )


def _workspace_context(selected, application_id=None):
    """Everything ``_workspace.html`` needs for one scope and selection.

    Read-only. The selected application is looked up within the scope, so
    another opening's application is a 404. Its move actions come only from
    ``hiring.rules``: forward moves (including Hire) and ending moves.
    """
    openings = JobOpening.objects.annotate(
        active_count=Count(
            "applications", filter=Q(applications__stage__in=ACTIVE_STAGES)
        )
    ).order_by("title", "department", "pk")  # aggregates drop Meta.ordering

    applications = Application.objects.all()
    if selected is not None:
        applications = applications.filter(opening=selected)
    per_stage = dict(
        applications.order_by().values_list("stage").annotate(n=Count("pk"))
    )

    selected_application = None
    forward_moves, ending_moves = [], []
    undo_to = None
    if application_id is not None:
        selected_application = get_object_or_404(
            applications.select_related("candidate", "opening"), pk=application_id
        )
        for to in rules.allowed_moves(selected_application.stage):
            if to in rules.ENDINGS:
                ending_moves.append((to, rules.LABELS[to]))
            else:
                label = "Hire" if to == rules.HIRED else rules.LABELS[to]
                forward_moves.append((to, label))
        stage = selected_application.stage
        previous = selected_application.previous_stage
        if rules.undo_blocker(stage, previous) is None:
            undo_to = rules.LABELS[previous]

    return {
        "openings": openings,
        "selected": selected,
        "scope": _scope_value(selected),
        "selected_application": selected_application,
        "forward_moves": forward_moves,
        "ending_moves": ending_moves,
        "undo_to": undo_to,
        "stage_counts": [(stage, per_stage.get(stage.value, 0)) for stage in Stage],
        "total": sum(per_stage.values()),
        "applications": applications.select_related("candidate", "opening").order_by(
            "candidate__last_name", "candidate__first_name", "pk"
        ),
    }


def _is_htmx(request):
    """An HTMX swap request (a history restore needs the full page instead)."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get(
        "HX-History-Restore-Request"
    )


@require_GET
def workspace(request):
    """The openings-first hiring workspace at ``/``. Read-only.

    ``?opening=all`` (the default) or ``?opening=<pk>`` picks the scope. The
    sidebar lists every opening with its active-applicant count (Applied
    through Offer only); the main area counts the scope's applications in all
    eight stages and lists them, one row per application. ``&application=<pk>``
    shows that application's details and its allowed move actions; it must
    belong to the scope, or the response is a 404. HTMX navigation gets just
    the ``_workspace.html`` partial; everything else, including an htmx history
    restore, gets the full page.
    """
    try:
        selected = _opening_for(request.GET.get("opening"))
        choice = request.GET.get("application")
        try:
            application_id = None if choice is None else int(choice)
        except ValueError:
            raise _BadParameter("Invalid application.") from None
    except _BadParameter as error:
        return HttpResponseBadRequest(str(error))

    context = _workspace_context(selected, application_id)
    template = (
        "hiring/_workspace.html" if _is_htmx(request) else "hiring/workspace.html"
    )
    response = render(request, template, context)
    patch_vary_headers(response, ("HX-Request", "HX-History-Restore-Request"))
    return response


@require_http_methods(["GET", "POST"])
def move_application(request, pk):
    """GET: the read-only move confirmation. POST: the confirmed move.

    ``opening`` is the workspace scope (the application must be in it, or 404).
    GET takes ``to`` and renders the confirmation, worded by the kind of move,
    carrying the stage seen now as ``expected_stage``; if the move isn't
    allowed (an outdated link), it shows the reason with Cancel only.

    POST takes ``to``, ``expected_stage`` and ``expected_changed_at`` (all
    required) and moves only through ``Application.move_to()``, which
    re-checks the rules, the stored stage and the stage-change timestamp, so
    nothing posted can bypass them.
    """
    data = request.POST if request.method == "POST" else request.GET
    try:
        selected, application = _scoped_application(data, pk)
    except _BadParameter as error:
        return HttpResponseBadRequest(str(error))
    to = data.get("to")

    if request.method == "GET":
        if to not in rules.STAGES:
            return HttpResponseBadRequest("Unknown stage.")
        reason = rules.why_not(application.stage, to)
        context = {
            "application": application,
            "scope": _scope_value(selected),
            "selection_url": _selection_url(selected, application),
            "to": to,
            "to_label": rules.LABELS[to],
            "from_label": rules.LABELS[application.stage],
            "reason": reason,
            "kind": None if reason else rules.kind_of(application.stage, to),
            "skipped": [] if reason else rules.skipped_stages(application.stage, to),
        }
        template = (
            "hiring/_move_confirm_modal.html"
            if request.headers.get("HX-Request")
            else "hiring/move_confirm_page.html"
        )
        return render(request, template, context)

    expected = data.get("expected_stage")
    if not to or not expected:
        return HttpResponseBadRequest("Give both to and expected_stage.")
    try:
        changed_at = _changed_at(data.get("expected_changed_at"))
    except _BadParameter as error:
        return HttpResponseBadRequest(str(error))
    try:
        application.move_to(
            to, request.user, expected_stage=expected, expected_changed_at=changed_at
        )
    except InvalidMove as error:
        level, text = messages.ERROR, str(error)
    else:
        level = messages.SUCCESS
        text = (
            f"Moved {application.candidate} from {rules.LABELS[expected]} "
            f"to {rules.LABELS[to]}."
        )
    return _stage_change_response(request, selected, application, level, text)


@require_POST
def undo_application(request, pk):
    """POST only: Undo the application's latest move, with no confirmation.

    Takes ``expected_stage`` and ``expected_changed_at`` (both required: the
    state shown with the Undo button) and ``opening`` (the scope). Undo goes
    only through ``Application.undo()``, which returns to the *stored*
    previous stage, so nothing posted chooses the destination; it refuses a
    stale state or an ineligible history. Responds like a move.
    """
    try:
        selected, application = _scoped_application(request.POST, pk)
        expected = request.POST.get("expected_stage")
        if not expected:
            raise _BadParameter("Give expected_stage.")
        changed_at = _changed_at(request.POST.get("expected_changed_at"))
    except _BadParameter as error:
        return HttpResponseBadRequest(str(error))
    try:
        application.undo(
            request.user, expected_stage=expected, expected_changed_at=changed_at
        )
    except InvalidMove as error:
        level, text = messages.ERROR, str(error)
    else:
        level = messages.SUCCESS
        text = (
            f"Undid the last change. {application.candidate} is back in "
            f"{rules.LABELS[application.stage]}."
        )
    return _stage_change_response(request, selected, application, level, text)


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
