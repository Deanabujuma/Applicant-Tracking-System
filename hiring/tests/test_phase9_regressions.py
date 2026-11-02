"""Phase 9 regression tests: Undo access, timestamps, panel, and structure."""

import datetime
import itertools
import re
from html import unescape

import pytest
from django.test import Client
from django.utils import timezone

from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import Application, InvalidMove, Stage, StaleMove
from hiring.tests.test_phase8_regressions import FormTree
from hiring.tests.test_stage_moves import (
    LONG_AGO,
    alerts,
    confirm_form,
    confirm_url,
    dialog,
    hidden,
    move_url,
    oob,
    post_data,
    sidebar_count,
)
from hiring.tests.test_undo_workspace import (
    last_change,
    undo_data,
    undo_form,
    undo_url,
)
from hiring.tests.test_workspace_detail import detail_panel, field
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
PAGE_AND_HTMX = pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])


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
def other_client(other_employee):
    other = Client()
    other.force_login(other_employee)
    return other


@pytest.fixture
def analyst():
    return JobOpening.objects.create(title="Data Analyst", department="Finance")


@pytest.fixture
def designer():
    return JobOpening.objects.create(title="Designer", department="Art")


@pytest.fixture
def make(employee, analyst):
    """An application at ``stage`` with ``previous`` recorded, at LONG_AGO."""
    count = iter(range(200))

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


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def stored(application):
    return Application.objects.get(pk=application.pk)


def panel_of(page):
    return detail_panel(page)[1]


def selection(application, scope="all"):
    return f"/?opening={scope}&application={application.pk}"


def ids(page, name):
    return len(re.findall(rf'\bid="{name}"', page))


# --- Access -----------------------------------------------------------------


@PAGE_AND_HTMX
def test_anonymous_visitors_cannot_undo(client, make, headers):
    application = make(S.SCREENING, S.APPLIED)
    before = snapshot()

    response = client.post(undo_url(application), undo_data(application), **headers)

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/?next=")
    assert snapshot() == before


@PAGE_AND_HTMX
def test_deactivated_employees_cannot_undo(client, employee, make, headers):
    client.force_login(employee)
    employee.is_active = False
    employee.save()
    application = make(S.SCREENING, S.APPLIED)
    before = snapshot()

    response = client.post(undo_url(application), undo_data(application), **headers)

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert snapshot() == before


@pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
def test_undo_endpoint_is_post_only(employee_client, make, method):
    application = make(S.SCREENING, S.APPLIED)
    before = snapshot()

    for headers in ({}, HTMX):
        response = getattr(employee_client, method)(undo_url(application), **headers)
        assert response.status_code == 405

    assert snapshot() == before


@PAGE_AND_HTMX
def test_csrf_is_enforced_for_undo(employee, make, headers):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(employee)
    application = make(S.SCREENING, S.APPLIED)
    before = snapshot()

    for extra in ({}, {"csrfmiddlewaretoken": "forged"}):
        response = csrf_client.post(
            undo_url(application), {**undo_data(application), **extra}, **headers
        )
        assert response.status_code == 403

    assert snapshot() == before


# --- Timestamps -------------------------------------------------------------


BAD_TIMESTAMPS = [
    None,  # missing
    "",
    "yesterday",
    "2026-13-01T10:00:00+00:00",  # no thirteenth month
    "2026-11-01T10:00:00",  # time-zone naive
]


@pytest.mark.parametrize("value", BAD_TIMESTAMPS, ids=repr)
@PAGE_AND_HTMX
def test_bad_timestamps_are_400_for_undo_and_moves(
    employee_client, make, value, headers
):
    undoable = make(S.SCREENING, S.APPLIED)
    movable = make(S.APPLIED)
    before = snapshot()

    for url, data in (
        (undo_url(undoable), undo_data(undoable)),
        (move_url(movable), post_data(S.SCREENING, S.APPLIED)),
    ):
        if value is None:
            del data["expected_changed_at"]
        else:
            data["expected_changed_at"] = value
        assert employee_client.post(url, data, **headers).status_code == 400, url

    assert snapshot() == before


def test_outdated_but_valid_timestamps_are_stale(employee, make):
    undoable = make(S.SCREENING, S.APPLIED)
    movable = make(S.APPLIED)
    older = LONG_AGO - datetime.timedelta(days=1)
    before = snapshot()

    with pytest.raises(StaleMove):
        stored(undoable).undo(
            employee, expected_stage=S.SCREENING, expected_changed_at=older
        )
    with pytest.raises(StaleMove):
        stored(movable).move_to(
            S.SCREENING, employee, expected_stage=S.APPLIED, expected_changed_at=older
        )

    assert snapshot() == before


@PAGE_AND_HTMX
def test_outdated_timestamp_posts_are_refused_with_an_error(
    employee_client, make, headers
):
    undoable = make(S.SCREENING, S.APPLIED)
    movable = make(S.APPLIED)
    older = LONG_AGO - datetime.timedelta(days=1)
    before = snapshot()

    for url, data in (
        (undo_url(undoable), undo_data(undoable, changed_at=older)),
        (move_url(movable), post_data(S.SCREENING, S.APPLIED, changed_at=older)),
    ):
        response = employee_client.post(url, data, **headers)
        if headers:
            [(kind, _)] = alerts(oob(response.content.decode(), "messages"))
        else:
            [(kind, _)] = alerts(employee_client.get(response.url).content.decode())
        assert kind == "alert-error"

    assert snapshot() == before


def test_old_confirmation_cannot_exploit_move_undo_and_return(
    employee_client, other_client, other_employee, make
):
    """Opened at Screening; meanwhile someone rejects it and undoes that, over
    HTTP, so it's at Screening again. The old confirmation must be refused."""
    application = make(S.SCREENING, S.APPLIED)
    modal = dialog(
        employee_client.get(confirm_url(application, S.OFFER), **HTMX).content.decode()
    )
    _, body = confirm_form(modal)
    old_form = {
        name: unescape(hidden(body, name))
        for name in ("to", "expected_stage", "expected_changed_at", "opening")
    }

    other_client.post(
        move_url(application),
        post_data(S.REJECTED, S.SCREENING),
        **HTMX,
    )
    after_reject = stored(application)
    assert after_reject.stage == S.REJECTED
    other_client.post(undo_url(application), undo_data(after_reject), **HTMX)
    back = stored(application)
    assert (back.stage, back.previous_stage) == (S.SCREENING, None)
    newer = snapshot()

    response = employee_client.post(move_url(application), old_form, **HTMX)

    assert snapshot() == newer
    [(kind, message)] = alerts(oob(response.content.decode(), "messages"))
    assert kind == "alert-error"
    assert "changed" in unescape(message)
    assert stored(application).stage_changed_by == other_employee


# --- Never undoable ---------------------------------------------------------


@PAGE_AND_HTMX
def test_hired_is_never_undoable_even_by_forged_posts(
    employee_client, employee, make, headers
):
    application = make(S.HIRED, S.OFFER)
    before = snapshot()

    with pytest.raises(InvalidMove, match="permanent"):
        stored(application).undo(
            employee, expected_stage=S.HIRED, expected_changed_at=LONG_AGO
        )
    for data in (
        undo_data(application),  # its real, current state
        undo_data(application, stage=S.OFFER),  # pretending it's still at Offer
        {**undo_data(application), "to": S.OFFER, "previous_stage": S.OFFER},
    ):
        employee_client.post(undo_url(application), data, **headers)
    assert snapshot() == before
    assert (
        undo_form(
            panel_of(employee_client.get(selection(application)).content.decode())
        )
        is None
    )


@pytest.mark.parametrize(
    ("stage", "previous"),
    [
        (S.APPLIED, None),
        (S.REJECTED, None),
        (S.INTERVIEW, S.OFFER),  # recorded a backward "move"
        (S.REJECTED, S.HIRED),  # recorded a move out of Hired
        (S.APPLIED, S.SCREENING),  # recorded a move into Applied
    ],
    ids=lambda v: "none" if v is None else v.value,
)
def test_no_undo_without_an_eligible_recorded_move(
    employee_client, make, stage, previous
):
    application = make(stage, previous)
    before = snapshot()

    page = employee_client.get(selection(application)).content.decode()
    assert undo_form(panel_of(page)) is None
    response = employee_client.post(
        undo_url(application), undo_data(application), **HTMX
    )
    [(kind, message)] = alerts(oob(response.content.decode(), "messages"))
    assert kind == "alert-error"
    assert unescape(message) == rules.undo_blocker(stage, previous)

    assert snapshot() == before


# --- Successful Undo --------------------------------------------------------


def test_undo_clears_previous_stage_records_who_and_blocks_a_second(
    employee_client, employee, make
):
    application = make(S.OFFER, S.INTERVIEW)
    started = timezone.now()

    employee_client.post(undo_url(application), undo_data(application), **HTMX)

    after = stored(application)
    assert (after.stage, after.previous_stage) == (S.INTERVIEW, None)
    assert after.stage_changed_by == employee
    assert after.stage_changed_at >= started
    assert after.updated_at >= started

    # A second Undo, even with the new (current) state, is refused.
    before = snapshot()
    response = employee_client.post(undo_url(application), undo_data(after), **HTMX)
    [(kind, message)] = alerts(oob(response.content.decode(), "messages"))
    assert kind == "alert-error"
    assert "Nothing to undo" in unescape(message)
    assert snapshot() == before


def test_last_stage_change_line_tracks_moves_undo_and_refusals(
    employee_client, other_client, make
):
    application = make(S.APPLIED)

    # A move by jsmith.
    page = employee_client.post(
        move_url(application), post_data(S.SCREENING, S.APPLIED), **HTMX
    ).content.decode()
    moved = stored(application)
    text, shown = last_change(panel_of(page))
    assert "jsmith" in text
    assert shown == moved.stage_changed_at

    # Undo by other.
    other_client.post(undo_url(application), undo_data(moved), **HTMX)
    undone = stored(application)
    page = employee_client.get(selection(application)).content.decode()
    text, shown = last_change(panel_of(page))
    assert "other" in text
    assert shown == undone.stage_changed_at

    # jsmith's stale Undo (from the moved state) is refused; the line stays.
    page = employee_client.post(
        undo_url(application), undo_data(moved), **HTMX
    ).content.decode()
    text, shown = last_change(panel_of(page))
    assert "other" in text
    assert "jsmith" not in text
    assert shown == undone.stage_changed_at
    assert stored(application).stage_changed_at == undone.stage_changed_at


def test_htmx_undo_updates_everything_in_all_openings(
    employee_client, make, analyst, designer
):
    application = make(S.WITHDRAWN, S.FINAL_REVIEW)
    make(S.SCREENING)
    make(S.OFFER, None, designer)

    response = employee_client.post(
        undo_url(application), undo_data(application, "all"), **HTMX
    )

    page = response.content.decode()
    assert page.strip().startswith('<div id="workspace"')
    assert current_hrefs(page) == ["/?opening=all"]
    for opening in (analyst, designer):
        assert sidebar_count(page, opening) == opening.applications.active().count()
    assert sidebar_count(page, analyst) == 2
    summary = stage_summary(page)
    for stage in Stage:
        assert (
            summary[stage.value][1] == Application.objects.filter(stage=stage).count()
        )
    assert total(page) == 3
    pk, panel = detail_panel(page)
    assert pk == application.pk
    assert "Final Review" in field(panel, "Stage")
    assert re.match(r"\s*</div>", oob(page, "modal"))
    assert [kind for kind, _ in alerts(page)] == ["alert-success"]
    later = employee_client.get(selection(application)).content.decode()
    assert alerts(later) == []


@pytest.mark.parametrize("valid", [True, False], ids=["undone", "refused"])
def test_non_htmx_undo_keeps_scope_and_selection(employee_client, make, analyst, valid):
    application = make(S.REJECTED, S.SCREENING)
    scope = str(analyst.pk)
    data = undo_data(application, scope)
    if not valid:
        data["expected_changed_at"] = timezone.now().isoformat()

    response = employee_client.post(undo_url(application), data, follow=True)

    assert response.redirect_chain == [(selection(application, scope), 302)]
    page = response.content.decode()
    assert current_hrefs(page) == [f"/?opening={scope}"]
    assert detail_panel(page)[0] == application.pk
    [(kind, _)] = alerts(page)
    assert kind == ("alert-success" if valid else "alert-error")
    assert (
        alerts(employee_client.get(selection(application, scope)).content.decode())
        == []
    )
    assert stored(application).stage == (S.SCREENING if valid else S.REJECTED)


# --- Structure ---------------------------------------------------------------


def test_every_full_workspace_page_has_one_of_each_container(employee_client, make):
    undoable = make(S.SCREENING, S.APPLIED)
    hired = make(S.HIRED, S.OFFER)

    for url in ("/", "/?opening=all", selection(undoable), selection(hired)):
        for headers in ({}, RESTORE):
            page = employee_client.get(url, **headers).content.decode()
            assert "<html" in page
            assert (
                ids(page, "workspace"),
                ids(page, "modal"),
                ids(page, "messages"),
            ) == (
                1,
                1,
                1,
            ), url


def test_exactly_one_undo_form_only_when_eligible(employee_client, make):
    """Every stage with every possible recorded previous stage."""
    for stage, previous in itertools.product(Stage, [None, *Stage]):
        application = make(stage, previous)
        page = employee_client.get(selection(application)).content.decode()
        panel = panel_of(page)
        eligible = rules.undo_blocker(stage, previous) is None
        assert panel.count('id="undo-form"') == int(eligible), (stage, previous)
        assert ("Undo" in panel) is eligible, (stage, previous)


@PAGE_AND_HTMX
def test_panel_has_only_the_undo_form_and_no_nested_forms(
    employee_client, make, headers
):
    application = make(S.OFFER, S.INTERVIEW)

    page = employee_client.get(selection(application), **headers).content.decode()
    panel = panel_of(page)

    assert len(re.findall(r"<form\b", panel)) == 1
    assert len(re.findall(r"<button\b", panel)) == 1  # the Undo button
    assert re.findall(r'hx-post="([^"]+)"', panel) == [undo_url(application)]
    assert "hx-delete" not in panel
    assert "hx-put" not in panel
    tree = FormTree()
    tree.feed(page)
    assert all(ancestors.count("form") == 0 for _, ancestors in tree.forms)
    # The full page also has the header's Log out form, nothing else.
    assert len(tree.forms) == (1 if headers else 2)


def test_gets_never_change_records(employee_client, make):
    applications = [
        make(S.SCREENING, S.APPLIED),
        make(S.HIRED, S.OFFER),
        make(S.APPLIED),
    ]
    before = snapshot()

    for application in applications:
        for headers in ({}, HTMX, RESTORE):
            employee_client.get(selection(application), **headers)
            for to in Stage:
                employee_client.get(confirm_url(application, to), **headers)
            employee_client.get(undo_url(application), **headers)  # 405

    assert snapshot() == before


# --- Phase 8 still intact ---------------------------------------------------


def test_phase8_move_flow_cancel_and_terminal_protection_still_work(
    employee_client, make
):
    application = make(S.APPLIED)
    hired = make(S.HIRED, S.OFFER)

    modal = dialog(
        employee_client.get(
            confirm_url(application, S.INTERVIEW), **HTMX
        ).content.decode()
    )
    assert re.search(r'<form method="dialog">\s*<button[^>]*>Cancel</button>', modal)
    assert "Skip ahead?" in modal
    _, body = confirm_form(modal)
    form = {
        name: unescape(hidden(body, name))
        for name in ("to", "expected_stage", "expected_changed_at", "opening")
    }
    page = employee_client.post(move_url(application), form, **HTMX).content.decode()
    assert stored(application).stage == S.INTERVIEW
    assert undo_form(panel_of(page)) is not None  # the move earned an Undo

    before = snapshot()
    for to in Stage:
        modal = dialog(
            employee_client.get(confirm_url(hired, to), **HTMX).content.decode()
        )
        assert confirm_form(modal) is None
        employee_client.post(move_url(hired), post_data(to, S.HIRED), **HTMX)
    assert snapshot() == before
