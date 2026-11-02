"""Phase 9 Test 3: Undo and last-change info in the workspace, plus Option B
(moves also check the stage-change timestamp)."""

import datetime
import inspect
import re
from html import unescape

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from candidates.models import Candidate, Source
from hiring.models import Application, Stage, StaleMove
from hiring.tests.test_stage_moves import (
    alerts,
    confirm_form,
    confirm_url,
    dialog,
    hidden,
    move_url,
    oob,
    sidebar_count,
)
from hiring.tests.test_workspace_detail import detail_panel, field
from hiring.tests.test_workspace_selection import (
    HTMX,
    attr,
    current_hrefs,
    stage_summary,
    total,
)
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
LONG_AGO = timezone.now() - datetime.timedelta(days=3)


# --- Readers ----------------------------------------------------------------


def undo_url(application):
    return f"/applications/{application.pk}/undo/"


def undo_form(panel):
    """(attributes, body) of the panel's Undo form, or None."""
    found = re.findall(
        r'<form\b([^>]*\bid="undo-form"[^>]*)>(.*?)</form>', panel, re.DOTALL
    )
    assert len(found) <= 1
    return found[0] if found else None


def token(application):
    """The stored stage-change timestamp, as the database has it now."""
    return Application.objects.get(pk=application.pk).stage_changed_at


def parse(value):
    return datetime.datetime.fromisoformat(unescape(value))


def last_change(panel):
    """(text, datetime) of the panel's "Last stage change" entry."""
    text = field(panel, "Last stage change")
    match = re.search(r'<time\b[^>]*\bdatetime="([^"]+)"', text)
    assert match, "no <time datetime=…> in Last stage change"
    return text, parse(match.group(1))


def undo_data(application, scope="all", *, stage=None, changed_at=None):
    return {
        "expected_stage": stage or application.stage,
        "expected_changed_at": (changed_at or application.stage_changed_at).isoformat(),
        "opening": scope,
    }


# --- Data -------------------------------------------------------------------


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def other_employee(django_user_model):
    return django_user_model.objects.create_user(username="other")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def analyst():
    return JobOpening.objects.create(title="Data Analyst", department="Finance")


@pytest.fixture
def make(employee, analyst):
    """An application at ``stage`` with ``previous`` recorded, changed long ago."""
    count = iter(range(100))

    def make_application(stage, previous=None, opening=None):
        n = next(count)
        application = Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=f"Person{n}",
                last_name="Doe",
                email=f"person{n}@example.com",
                source=Source.REFERRAL,
            ),
            opening=opening or analyst,
            stage_changed_by=employee,
        )
        Application.objects.filter(pk=application.pk).update(
            stage=stage,
            previous_stage=previous,
            stage_changed_at=LONG_AGO,
            updated_at=LONG_AGO,
        )
        application.refresh_from_db()
        return application

    return make_application


def someone_else_changes(application, employee, stage, previous):
    """Another employee's move or Undo: a new stage state and a new timestamp."""
    Application.objects.filter(pk=application.pk).update(
        stage=stage,
        previous_stage=previous,
        stage_changed_by=employee,
        stage_changed_at=timezone.now(),
        updated_at=timezone.now(),
    )


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def panel_for(client, application, scope="all", **headers):
    page = client.get(
        f"/?opening={scope}&application={application.pk}", **headers
    ).content.decode()
    pk, panel = detail_panel(page)
    assert pk == application.pk
    return page, panel


# --- Last stage change ------------------------------------------------------


def test_last_stage_change_before_any_move_is_the_creator(
    employee_client, django_user_model, analyst
):
    recruiter = django_user_model.objects.create_user(username="recruiter")
    application = Application.objects.create(
        candidate=Candidate.objects.create(
            first_name="Ana",
            last_name="Doe",
            email="ana@example.com",
            source=Source.REFERRAL,
        ),
        opening=analyst,
        stage_changed_by=recruiter,
    )

    _, panel = panel_for(employee_client, application)

    text, shown = last_change(panel)
    assert "recruiter" in text
    assert shown == application.stage_changed_at
    assert abs(application.stage_changed_at - application.created_at) < (
        datetime.timedelta(seconds=1)
    )
    assert undo_form(panel) is None  # never moved: nothing to undo


# --- Undo shown only when allowed -------------------------------------------


@pytest.mark.parametrize(
    ("stage", "previous", "shown"),
    [
        (S.SCREENING, S.APPLIED, True),
        (S.OFFER, S.APPLIED, True),  # after a skip
        (S.REJECTED, S.INTERVIEW, True),
        (S.WITHDRAWN, S.OFFER, True),
        (S.HIRED, S.OFFER, False),  # permanent
        (S.APPLIED, None, False),  # never moved
        (S.SCREENING, None, False),  # just undone
        (S.SCREENING, S.WITHDRAWN, False),  # impossible history
    ],
)
@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_undo_form_appears_only_when_the_rules_allow(
    employee_client, make, analyst, stage, previous, shown, headers
):
    application = make(stage, previous)
    scope = str(analyst.pk)
    before = snapshot()

    _, panel = panel_for(employee_client, application, scope, **headers)

    form = undo_form(panel)
    if not shown:
        assert form is None
        assert "Undo" not in panel
        assert "<form" not in panel
    else:
        assert form is not None
        attrs, body = form
        assert attr(attrs, "method") == "post"
        assert attr(attrs, "action") == undo_url(application)
        assert attr(attrs, "hx-post") == undo_url(application)  # direct, no modal
        assert attr(attrs, "hx-target") == "#workspace"
        assert attr(attrs, "hx-swap") == "outerHTML"
        assert attr(attrs, "hx-get") is None
        assert "#modal" not in attrs
        assert "csrfmiddlewaretoken" in body
        assert hidden(body, "expected_stage") == stage
        assert parse(hidden(body, "expected_changed_at")) == LONG_AGO
        assert hidden(body, "opening") == scope
        assert re.search(r"<button\b[^>]*>[^<]*Undo[^<]*</button>", body)
        assert Stage(previous).label in panel  # where Undo will return to
        assert len(re.findall(r"<form\b", panel)) == 1  # the only form
    assert snapshot() == before  # workspace GETs stay read-only


# --- Successful Undo --------------------------------------------------------


def test_htmx_undo_refreshes_the_workspace(
    employee_client, employee, other_employee, make, analyst
):
    application = make(S.REJECTED, S.INTERVIEW)
    Application.objects.filter(pk=application.pk).update(
        stage_changed_by=other_employee
    )
    make(S.SCREENING)  # another active applicant
    scope = str(analyst.pk)
    page, panel = panel_for(employee_client, application, scope)
    assert sidebar_count(page, analyst) == 1
    started = timezone.now()

    response = employee_client.post(
        undo_url(application), undo_data(application, scope), **HTMX
    )

    assert response.status_code == 200
    page = response.content.decode()
    stored = Application.objects.get(pk=application.pk)
    assert (stored.stage, stored.previous_stage) == (S.INTERVIEW, None)
    assert stored.stage_changed_by == employee
    assert stored.stage_changed_at >= started

    assert page.strip().startswith('<div id="workspace"')
    assert current_hrefs(page) == [f"/?opening={scope}"]
    assert sidebar_count(page, analyst) == 2  # Interview is active again
    summary = stage_summary(page)
    assert (summary[S.REJECTED.value][1], summary[S.INTERVIEW.value][1]) == (0, 1)
    assert total(page) == 2
    pk, panel = detail_panel(page)
    assert pk == application.pk
    assert "Interview" in field(panel, "Stage")
    assert undo_form(panel) is None  # single use
    assert 'data-move-to="final_review"' in panel  # moves are available again
    text, shown = last_change(panel)
    assert "jsmith" in text
    assert shown == stored.stage_changed_at

    assert re.match(r"\s*</div>", oob(page, "modal"))
    [(kind, message)] = alerts(oob(page, "messages"))
    assert kind == "alert-success"
    assert str(application.candidate) in message
    assert "Interview" in message


def test_non_htmx_undo_redirects_to_the_selection(employee_client, make):
    application = make(S.WITHDRAWN, S.SCREENING)

    response = employee_client.post(
        undo_url(application), undo_data(application), follow=True
    )

    selection = f"/?opening=all&application={application.pk}"
    assert response.redirect_chain == [(selection, 302)]
    assert Application.objects.get(pk=application.pk).stage == S.SCREENING
    page = response.content.decode()
    [(kind, message)] = alerts(page)
    assert kind == "alert-success"
    assert "Screening" in message
    assert detail_panel(page)[0] == application.pk
    assert alerts(employee_client.get(selection).content.decode()) == []  # once


# --- Refused Undo -----------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "moved-by-other",
        "undone-by-other",
        "undone-then-moved-back",
        "hired",
        "nothing-to-undo",
        "forged-timestamp",
        "forged-stage",
    ],
)
@pytest.mark.parametrize("headers", [HTMX, {}], ids=["htmx", "page"])
def test_stale_or_unavailable_undo_changes_nothing(
    employee_client, other_employee, make, case, headers
):
    if case in ("hired", "nothing-to-undo"):
        application = make(
            *{"hired": (S.HIRED, S.OFFER), "nothing-to-undo": (S.SCREENING, None)}[case]
        )
        data = undo_data(application)
    else:
        application = make(S.SCREENING, S.APPLIED)
        data = undo_data(application)  # what the page showed
        if case == "moved-by-other":
            someone_else_changes(application, other_employee, S.INTERVIEW, S.SCREENING)
        elif case == "undone-by-other":
            someone_else_changes(application, other_employee, S.APPLIED, None)
        elif case == "undone-then-moved-back":  # same stage as the button again
            someone_else_changes(application, other_employee, S.SCREENING, S.APPLIED)
        elif case == "forged-timestamp":
            data = undo_data(application, changed_at=timezone.now())
        else:  # forged-stage
            data = undo_data(application, stage=S.OFFER)
    before = snapshot()

    response = employee_client.post(undo_url(application), data, **headers)

    assert snapshot() == before
    current = Application.objects.get(pk=application.pk)
    if headers:
        assert response.status_code == 200
        page = response.content.decode()
        assert page.strip().startswith('<div id="workspace"')
        pk, panel = detail_panel(page)
        assert pk == application.pk
        assert current.get_stage_display() in field(panel, "Stage")
        assert re.match(r"\s*</div>", oob(page, "modal"))
        [(kind, message)] = alerts(oob(page, "messages"))
    else:
        assert response.status_code == 302
        assert response.url == f"/?opening=all&application={application.pk}"
        [(kind, message)] = alerts(employee_client.get(response.url).content.decode())
    assert kind == "alert-error"
    assert message.strip()


def test_undo_ignores_a_forged_destination(employee_client, other_employee, make):
    application = make(S.OFFER, S.SCREENING)

    employee_client.post(
        undo_url(application),
        {
            **undo_data(application),
            "to": S.HIRED,
            "stage": S.HIRED,
            "previous_stage": S.APPLIED,
            "stage_changed_by": other_employee.pk,
        },
        **HTMX,
    )

    stored = Application.objects.get(pk=application.pk)
    assert (stored.stage, stored.previous_stage) == (S.SCREENING, None)
    assert stored.stage_changed_by_id != other_employee.pk


def test_bad_undo_requests_are_refused(employee_client, make, analyst):
    application = make(S.SCREENING, S.APPLIED)
    designer = JobOpening.objects.create(title="Designer", department="Art")
    missing = Application.objects.order_by("-pk").first().pk + 1
    before = snapshot()

    for headers in (HTMX, {}):
        post = employee_client.post
        assert (
            post(
                f"/applications/{missing}/undo/", undo_data(application), **headers
            ).status_code
            == 404
        )
        assert (
            post(
                undo_url(application),
                undo_data(application, str(designer.pk)),
                **headers,
            ).status_code
            == 404
        )
        for drop in ("expected_stage", "expected_changed_at"):
            data = undo_data(application)
            del data[drop]
            assert post(undo_url(application), data, **headers).status_code == 400, drop
        bad = {**undo_data(application), "expected_changed_at": "yesterday"}
        assert post(undo_url(application), bad, **headers).status_code == 400
        assert employee_client.get(undo_url(application), **headers).status_code == 405

    assert snapshot() == before


def test_undo_needs_login_and_csrf(client, employee, make):
    application = make(S.SCREENING, S.APPLIED)
    before = snapshot()

    response = client.post(undo_url(application), undo_data(application))
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(employee)
    assert (
        csrf_client.post(
            undo_url(application), undo_data(application), **HTMX
        ).status_code
        == 403
    )
    assert snapshot() == before

    _, panel = panel_for(csrf_client, application)
    _, body = undo_form(panel)
    response = csrf_client.post(
        undo_url(application),
        {
            "csrfmiddlewaretoken": hidden(body, "csrfmiddlewaretoken"),
            "expected_stage": hidden(body, "expected_stage"),
            "expected_changed_at": unescape(hidden(body, "expected_changed_at")),
            "opening": hidden(body, "opening"),
        },
        **HTMX,
    )
    assert response.status_code == 200
    assert Application.objects.get(pk=application.pk).stage == S.APPLIED


# --- Option B: moves check the timestamp too --------------------------------


def test_move_to_takes_and_checks_the_expected_timestamp(
    employee, other_employee, make
):
    assert "expected_changed_at" in inspect.signature(Application.move_to).parameters
    application = make(S.SCREENING, S.APPLIED)
    seen = application.stage_changed_at
    # Another employee rejects it and undoes that: back to Screening, new timestamp.
    someone_else_changes(application, other_employee, S.SCREENING, None)
    newer = snapshot()

    with pytest.raises(StaleMove):
        application.move_to(
            S.INTERVIEW, employee, expected_stage=S.SCREENING, expected_changed_at=seen
        )
    assert snapshot() == newer

    with CaptureQueriesContext(connection) as queries:
        application.move_to(
            S.INTERVIEW,
            employee,
            expected_stage=S.SCREENING,
            expected_changed_at=token(application),
        )
    writes = [
        q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("UPDATE")
    ]
    assert len(writes) == 1
    where = writes[0].upper().split(" WHERE ", 1)[1]
    assert '"STAGE"' in where
    assert '"STAGE_CHANGED_AT"' in where
    stored = Application.objects.get(pk=application.pk)
    assert (stored.stage, stored.previous_stage) == (S.INTERVIEW, S.SCREENING)


@pytest.mark.parametrize("headers", [HTMX, {}], ids=["htmx", "page"])
def test_move_confirmation_opened_before_a_move_and_undo_is_stale(
    employee_client, other_employee, make, headers
):
    application = make(S.SCREENING, S.APPLIED)
    modal = dialog(
        employee_client.get(
            confirm_url(application, S.INTERVIEW), **HTMX
        ).content.decode()
    )
    _, body = confirm_form(modal)
    assert parse(hidden(body, "expected_changed_at")) == LONG_AGO
    form = {
        name: unescape(hidden(body, name))
        for name in ("to", "expected_stage", "expected_changed_at", "opening")
    }
    # Meanwhile: rejected and undone by someone else, so back at Screening.
    someone_else_changes(application, other_employee, S.SCREENING, None)
    newer = snapshot()

    response = employee_client.post(move_url(application), form, **headers)

    assert snapshot() == newer  # the confirmation was stale
    if headers:
        [(kind, message)] = alerts(oob(response.content.decode(), "messages"))
    else:
        [(kind, message)] = alerts(employee_client.get(response.url).content.decode())
    assert kind == "alert-error"
    assert "changed" in unescape(message).lower()


def test_a_fresh_move_confirmation_still_works_and_earns_an_undo(
    employee_client, employee, make
):
    application = make(S.SCREENING, None)
    modal = dialog(
        employee_client.get(
            confirm_url(application, S.INTERVIEW), **HTMX
        ).content.decode()
    )
    _, body = confirm_form(modal)
    form = {
        name: unescape(hidden(body, name))
        for name in ("to", "expected_stage", "expected_changed_at", "opening")
    }

    page = employee_client.post(move_url(application), form, **HTMX).content.decode()

    stored = Application.objects.get(pk=application.pk)
    assert (stored.stage, stored.previous_stage) == (S.INTERVIEW, S.SCREENING)
    _, panel = detail_panel(page)
    _, undo_body = undo_form(panel)
    assert parse(hidden(undo_body, "expected_changed_at")) == stored.stage_changed_at
    text, shown = last_change(panel)
    assert "jsmith" in text
    assert shown == stored.stage_changed_at
