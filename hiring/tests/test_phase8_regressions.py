"""Phase 8 regression tests: stage moves' access, structure, and safety."""

import datetime
import re
from html.parser import HTMLParser

import pytest
from django.test import Client

from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import ACTIVE_STAGES, Application, InvalidMove, Stage
from hiring.tests.test_stage_moves import (
    LONG_AGO,
    alerts,
    confirm_form,
    confirm_url,
    dialog,
    move_url,
    oob,
    post_data,
    sidebar_count,
)
from hiring.tests.test_workspace_detail import detail_panel
from hiring.tests.test_workspace_selection import (
    HTMX,
    current_hrefs,
    stage_summary,
    total,
)
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
RESTORE = {**HTMX, "HTTP_HX_HISTORY_RESTORE_REQUEST": "true"}
TERMINAL = [S.HIRED, S.REJECTED, S.WITHDRAWN]


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )


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
def designer():
    return JobOpening.objects.create(title="Designer", department="Art")


@pytest.fixture
def make(employee, analyst):
    count = iter(range(100))

    def make_application(stage, opening=None):
        n = next(count)
        application = Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=f"Person{n}",
                last_name="Doe",
                email=f"person{n}@example.com",
                source=Source.REFERRAL,
            ),
            opening=opening or analyst,
            stage=stage,
            stage_changed_by=employee,
        )
        Application.objects.filter(pk=application.pk).update(
            stage_changed_at=LONG_AGO, updated_at=LONG_AGO
        )
        application.refresh_from_db()
        return application

    return make_application


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def row(application):
    return Application.objects.filter(pk=application.pk).values().get()


# --- Rules and Stage stay in step -------------------------------------------


def test_rules_labels_match_stage_choices_exactly():
    assert list(rules.LABELS.items()) == [(s.value, s.label) for s in Stage]
    assert rules.STAGES == tuple(Stage.values)
    assert rules.ACTIVE == tuple(Stage.values[:5])
    assert ACTIVE_STAGES == (
        S.APPLIED,
        S.SCREENING,
        S.INTERVIEW,
        S.FINAL_REVIEW,
        S.OFFER,
    )
    assert all(isinstance(stage, Stage) for stage in ACTIVE_STAGES)


# --- Access -----------------------------------------------------------------


def move_requests(application):
    return [
        ("get", confirm_url(application, S.SCREENING), {}),
        ("post", move_url(application), post_data(S.SCREENING, S.APPLIED)),
    ]


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_anonymous_visitors_are_sent_to_login(client, make, headers):
    application = make(S.APPLIED)
    before = snapshot()

    for method, url, data in move_requests(application):
        response = getattr(client, method)(url, data, **headers)
        assert response.status_code == 302, (method, url)
        assert response.url.startswith("/accounts/login/?next=")

    assert snapshot() == before


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_deactivated_employees_are_sent_to_login(client, employee, make, headers):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    application = make(S.APPLIED)
    before = snapshot()

    for method, url, data in move_requests(application):
        response = getattr(client, method)(url, data, **headers)
        assert response.status_code == 302, (method, url)
        assert response.url.startswith("/accounts/login/")

    assert snapshot() == before


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_unsupported_methods_return_405(employee_client, make, method):
    application = make(S.APPLIED)
    before = snapshot()

    response = getattr(employee_client, method)(move_url(application))

    assert response.status_code == 405
    assert snapshot() == before


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_csrf_is_enforced_for_moves(employee, make, headers):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(employee)
    application = make(S.APPLIED)
    before = snapshot()

    response = csrf_client.post(
        move_url(application), post_data(S.SCREENING, S.APPLIED), **headers
    )
    assert response.status_code == 403
    response = csrf_client.post(
        move_url(application),
        {**post_data(S.SCREENING, S.APPLIED), "csrfmiddlewaretoken": "forged"},
        **headers,
    )
    assert response.status_code == 403
    assert snapshot() == before


# --- Read-only confirmations and Cancel -------------------------------------


@pytest.mark.parametrize("stage", list(Stage), ids=lambda s: s.value)
def test_viewing_any_confirmation_changes_nothing(employee_client, make, stage):
    application = make(stage)
    before = snapshot()

    for to in Stage:
        for headers in ({}, HTMX):
            for _ in range(2):
                response = employee_client.get(confirm_url(application, to), **headers)
                assert response.status_code == 200

    assert snapshot() == before  # including every timestamp


class FormTree(HTMLParser):
    """Records, for each <form>, its method and its open ancestor tags."""

    def __init__(self):
        super().__init__()
        self.stack, self.forms = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "input":  # void element
            return
        if tag == "form":
            self.forms.append((dict(attrs), [t for t, _ in self.stack]))
        self.stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
@pytest.mark.parametrize("to", [S.SCREENING, S.REJECTED])
def test_cancel_closes_the_native_dialog_without_a_request(
    employee_client, make, headers, to
):
    application = make(S.APPLIED)
    page = employee_client.get(confirm_url(application, to), **headers).content.decode()
    tree = FormTree()
    tree.feed(page)

    dialog_forms = [(a, anc) for a, anc in tree.forms if "dialog" in anc]
    assert len(dialog_forms) == 2  # Cancel and Confirm, both inside <dialog>
    for _, ancestors in dialog_forms:
        assert ancestors.count("form") == 0  # no nested forms
    [(cancel, ancestors)] = [
        (a, anc) for a, anc in dialog_forms if a["method"] == "dialog"
    ]
    # method="dialog" closes its nearest <dialog> ancestor, here an open one.
    assert ancestors.count("dialog") == 1
    assert re.search(r"<dialog\b[^>]*\bopen\b", page)
    # Cancel sends nothing: no action, no HTMX request.
    assert not any(key in cancel for key in ("action", "hx-post", "hx-get"))
    modal = dialog(page)
    assert re.search(
        r'<form method="dialog">\s*<button type="submit"[^>]*>Cancel</button>\s*</form>',
        modal,
    )


# --- Edits never move stages ------------------------------------------------


def test_editing_candidate_or_opening_keeps_every_stage(employee_client, make, analyst):
    applications = [make(stage) for stage in Stage]
    candidate = applications[0].candidate
    stage_fields = (
        "stage",
        "previous_stage",
        "stage_changed_by_id",
        "stage_changed_at",
    )
    before = {a.pk: {f: row(a)[f] for f in stage_fields} for a in applications}

    response = employee_client.post(
        f"/candidates/{candidate.pk}/edit/",
        {
            "first_name": "Renamed",
            "last_name": "Doe",
            "email": candidate.email,
            "phone": "",
            "source": Source.JOB_BOARD,
            "source_detail": "",
            "notes": "",
            "stage": S.HIRED,  # forged: not a candidate field
        },
    )
    assert response.status_code == 302
    response = employee_client.post(
        f"/openings/{analyst.pk}/edit/",
        {
            "title": "Senior Data Analyst",
            "department": "Finance",
            "location": "Remote",
            "description": "",
            "stage": S.HIRED,  # forged
        },
    )
    assert response.status_code == 302

    assert Candidate.objects.get(pk=candidate.pk).first_name == "Renamed"
    assert JobOpening.objects.get(pk=analyst.pk).title == "Senior Data Analyst"
    after = {a.pk: {f: row(a)[f] for f in stage_fields} for a in applications}
    assert after == before


# --- Terminal stages --------------------------------------------------------


@pytest.mark.parametrize("stage", TERMINAL, ids=lambda s: s.value)
def test_terminal_stages_stay_terminal_in_model_and_ui(
    employee_client, employee, make, stage
):
    application = make(stage)
    before = snapshot()

    for to in Stage:
        with pytest.raises(InvalidMove):
            view = Application.objects.get(pk=application.pk)
            view.move_to(
                to,
                employee,
                expected_stage=stage,
                expected_changed_at=view.stage_changed_at,
            )
        for headers in ({}, HTMX):
            employee_client.post(move_url(application), post_data(to, stage), **headers)
            modal = dialog(
                employee_client.get(
                    confirm_url(application, to), **headers
                ).content.decode()
            )
            assert confirm_form(modal) is None
    assert snapshot() == before

    page = employee_client.get(
        f"/?opening=all&application={application.pk}"
    ).content.decode()
    assert "data-move-to" not in detail_panel(page)[1]


# --- Messages, selection, and counts after a move ---------------------------


@pytest.mark.parametrize("outcome", ["success", "error"])
def test_htmx_message_appears_exactly_once(employee_client, make, analyst, outcome):
    application = make(S.APPLIED)
    expected = S.APPLIED if outcome == "success" else S.SCREENING  # stale
    scope = str(analyst.pk)

    response = employee_client.post(
        move_url(application), post_data(S.SCREENING, expected, scope), **HTMX
    )

    page = response.content.decode()
    assert [kind for kind, _ in alerts(page)] == [f"alert-{outcome}"]
    later = employee_client.get(f"/?opening={scope}&application={application.pk}")
    assert alerts(later.content.decode()) == []  # nothing left queued


def test_non_htmx_error_message_appears_exactly_once(employee_client, make):
    application = make(S.SCREENING)

    response = employee_client.post(
        move_url(application), post_data(S.APPLIED, S.SCREENING), follow=True
    )

    assert [kind for kind, _ in alerts(response.content.decode())] == ["alert-error"]
    assert (
        alerts(employee_client.get(response.redirect_chain[-1][0]).content.decode())
        == []
    )


@pytest.mark.parametrize("valid", [True, False], ids=["moved", "refused"])
@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_selection_and_scope_survive_a_move(
    employee_client, make, analyst, designer, valid, headers
):
    application = make(S.INTERVIEW)
    make(S.APPLIED, designer)  # another opening's application
    scope = str(analyst.pk)
    to = S.OFFER if valid else S.APPLIED

    response = employee_client.post(
        move_url(application), post_data(to, S.INTERVIEW, scope), **headers
    )

    selection = f"/?opening={scope}&application={application.pk}"
    if headers:
        page = response.content.decode()
    else:
        assert response.status_code == 302
        assert response.url == selection
        page = employee_client.get(response.url).content.decode()
    assert current_hrefs(page) == [f"/?opening={scope}"]
    assert detail_panel(page)[0] == application.pk
    assert row(application)["stage"] == (S.OFFER if valid else S.INTERVIEW)


def test_refreshed_counts_match_the_database(employee_client, make, analyst, designer):
    moving = make(S.APPLIED)
    ending = make(S.INTERVIEW)
    make(S.OFFER)
    make(S.SCREENING, designer)

    employee_client.post(
        move_url(moving), post_data(S.OFFER, S.APPLIED, str(analyst.pk)), **HTMX
    )
    response = employee_client.post(
        move_url(ending), post_data(S.REJECTED, S.INTERVIEW, "all"), **HTMX
    )
    page = response.content.decode()

    for opening in (analyst, designer):
        assert sidebar_count(page, opening) == opening.applications.active().count()
    summary = stage_summary(page)  # All Openings scope
    for stage in Stage:
        assert (
            summary[stage.value][1] == Application.objects.filter(stage=stage).count()
        )
    assert total(page) == Application.objects.count() == 4
    assert summary[S.OFFER.value][1] == 2
    assert summary[S.REJECTED.value][1] == 1
    assert sidebar_count(page, analyst) == 2


# --- Page structure ---------------------------------------------------------


def ids(page, name):
    return len(re.findall(rf'\bid="{name}"', page))


def test_page_structure_for_every_kind_of_response(employee_client, make):
    application = make(S.APPLIED)
    selection = f"/?opening=all&application={application.pk}"

    full = employee_client.get(selection).content.decode()
    restore = employee_client.get(selection, **RESTORE).content.decode()
    for page in (full, restore):
        assert "<html" in page
        assert (ids(page, "workspace"), ids(page, "modal"), ids(page, "messages")) == (
            1,
            1,
            1,
        )

    partial = employee_client.get(selection, **HTMX).content.decode()
    assert "<html" not in partial
    assert (
        ids(partial, "workspace"),
        ids(partial, "modal"),
        ids(partial, "messages"),
    ) == (
        1,
        0,
        0,
    )

    modal = employee_client.get(confirm_url(application, S.SCREENING), **HTMX)
    modal = modal.content.decode()
    assert "<html" not in modal
    assert modal.count("<dialog") == 1
    assert ids(modal, "workspace") == ids(modal, "modal") == 0

    confirm_page = employee_client.get(confirm_url(application, S.SCREENING))
    confirm_page = confirm_page.content.decode()
    assert "<html" in confirm_page
    assert confirm_page.count("<dialog") == 1
    assert ids(confirm_page, "messages") == 1

    moved = employee_client.post(
        move_url(application), post_data(S.SCREENING, S.APPLIED), **HTMX
    ).content.decode()
    assert "<html" not in moved
    assert (ids(moved, "workspace"), ids(moved, "modal"), ids(moved, "messages")) == (
        1,
        1,
        1,
    )
    oob(moved, "modal")
    oob(moved, "messages")


# --- Forged, replayed, and stale submissions --------------------------------


def test_forged_extra_fields_are_ignored(employee_client, other_employee, make):
    application = make(S.APPLIED)

    employee_client.post(
        move_url(application),
        {
            **post_data(S.SCREENING, S.APPLIED),
            "stage": S.HIRED,
            "previous_stage": S.OFFER,
            "stage_changed_by": other_employee.pk,
            "employee": other_employee.pk,
        },
        **HTMX,
    )

    after = row(application)
    assert (after["stage"], after["previous_stage"]) == (S.SCREENING, S.APPLIED)
    assert after["stage_changed_by_id"] != other_employee.pk


@pytest.mark.parametrize(
    ("to", "expected"),
    [
        (S.HIRED, S.APPLIED),  # Hired before Offer
        (S.HIRED, S.OFFER),  # lying about the stage
        (S.APPLIED, S.APPLIED),  # same stage
        ("HIRED", S.APPLIED),  # wrong case
        ("hired ", S.APPLIED),  # padded
    ],
)
def test_forged_submissions_cannot_bypass_the_rules(
    employee_client, make, to, expected
):
    application = make(S.APPLIED)
    before = snapshot()

    for headers in ({}, HTMX):
        employee_client.post(move_url(application), post_data(to, expected), **headers)

    assert snapshot() == before


def test_replayed_or_late_confirmation_cannot_overwrite_a_newer_change(
    employee_client, other_employee, make
):
    application = make(S.APPLIED)
    other = Client()
    other.force_login(other_employee)
    # Both employees open the confirmation while it's in Applied.
    for client_ in (employee_client, other):
        modal = dialog(
            client_.get(confirm_url(application, S.SCREENING), **HTMX).content.decode()
        )
        assert 'name="expected_stage" value="applied"' in modal

    other.post(move_url(application), post_data(S.SCREENING, S.APPLIED), **HTMX)
    newer = snapshot()

    for data in (post_data(S.SCREENING, S.APPLIED), post_data(S.INTERVIEW, S.APPLIED)):
        response = employee_client.post(move_url(application), data, **HTMX)
        [(kind, text)] = alerts(response.content.decode())
        assert kind == "alert-error"
        assert "changed to Screening" in text

    assert snapshot() == newer
    assert row(application)["stage_changed_by_id"] == other_employee.pk


# --- Without HTMX -----------------------------------------------------------


def test_full_page_fallback_works_without_htmx(employee):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(employee)
    opening = JobOpening.objects.create(title="Analyst", department="IT")
    application = Application.objects.create(
        candidate=Candidate.objects.create(
            first_name="Ana",
            last_name="Doe",
            email="ana@example.com",
            source=Source.REFERRAL,
        ),
        opening=opening,
        stage=S.FINAL_REVIEW,
        stage_changed_by=employee,
    )
    scope = str(opening.pk)

    workspace = csrf_client.get(
        f"/?opening={scope}&application={application.pk}"
    ).content.decode()
    link = re.search(r'data-move-to="offer" href="([^"]+)"', workspace).group(1)
    page = csrf_client.get(link.replace("&amp;", "&")).content.decode()
    assert "<html" in page
    assert "Move forward?" in page
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    seen = re.search(r'name="expected_changed_at" value="([^"]+)"', page).group(1)

    response = csrf_client.post(
        move_url(application),
        {
            **post_data(
                S.OFFER,
                S.FINAL_REVIEW,
                scope,
                changed_at=datetime.datetime.fromisoformat(seen),
            ),
            "csrfmiddlewaretoken": token,
        },
        follow=True,
    )

    assert response.redirect_chain == [
        (f"/?opening={scope}&application={application.pk}", 302)
    ]
    assert row(application)["stage"] == S.OFFER
    [(kind, text)] = alerts(response.content.decode())
    assert kind == "alert-success"
    assert "from Final Review to Offer" in text
