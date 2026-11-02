"""Phase 10 regressions: search, stage filter and sort, kept through every
workspace path. Only gaps the three test-first files don't already cover."""

import datetime
import re
from html import unescape

import pytest
from django.utils.http import urlencode

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from hiring.tests.test_stage_moves import (
    action_links,
    alerts,
    confirm_form,
    dialog,
    hidden,
    oob,
    sidebar_count,
)
from hiring.tests.test_undo_workspace import undo_form
from hiring.tests.test_workspace_detail import detail_panel
from hiring.tests.test_workspace_filters import stage_link
from hiring.tests.test_workspace_selection import (
    HTMX,
    applicant_items,
    attr,
    sidebar_links,
)
from hiring.tests.test_workspace_sorting import sort_links
from hiring.tests.test_workspace_state import (
    LONG_AGO,
    RESTORE,
    STATE,
    form_fields,
    link_state,
    move_data,
    order,
    pks,
    search_box,
    search_form,
    split,
    undo_post,
)
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
# Characters that must survive URLs, HTML attributes and LIKE unchanged.
AWKWARD = 'a&b=c "d" <e> 50%+_'


# --- Data -------------------------------------------------------------------


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def data(employee):
    """Under STATE (q=doe, Screening, oldest change first): Data Analyst lists
    Ana, Ben, Fay (archived); All Openings adds Cara. Hal is Hired."""
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    designer = JobOpening.objects.create(title="Designer", department="Art")
    rows = {
        # name: (first, opening, stage, previous, days after LONG_AGO, archived)
        "ana": ("Ana", analyst, S.SCREENING, S.APPLIED, 1, False),
        "ben": ("Ben", analyst, S.SCREENING, None, 2, False),
        "fay": ("Fay", analyst, S.SCREENING, None, 3, True),
        "hal": ("Hal", analyst, S.HIRED, S.OFFER, 4, False),
        "cara": ("Cara", designer, S.SCREENING, None, 5, False),
    }
    made = {"analyst": analyst, "designer": designer}
    for name, (first, opening, stage, previous, days, archived) in rows.items():
        application = Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=first,
                last_name="Doe",
                email=f"{name}@example.com",
                source=Source.REFERRAL,
                is_archived=archived,
            ),
            opening=opening,
            stage=stage,
            stage_changed_by=employee,
        )
        Application.objects.filter(pk=application.pk).update(
            previous_stage=previous,
            stage_changed_at=LONG_AGO + datetime.timedelta(days=days),
        )
        application.refresh_from_db()
        made[name] = application
    return made


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def url(scope, application=None, **state):
    params = {"opening": scope}
    if application is not None:
        params["application"] = application.pk
    return "/?" + urlencode(params | {k: v for k, v in state.items() if v})


def move_url(application):
    return f"/applications/{application.pk}/move/"


def undo_url(application):
    return f"/applications/{application.pk}/undo/"


def state_requests(data):
    """Every kind of workspace request, each carrying the full state."""
    ana, scope = data["ana"], str(data["analyst"].pk)
    confirm = f"{move_url(ana)}?{urlencode({'to': 'interview', 'opening': scope})}"
    return [
        ("get", url(scope, ana, **STATE), {}),
        ("get", f"{confirm}&{urlencode(STATE)}", {}),
        ("post", move_url(ana), move_data(ana, S.INTERVIEW, scope, **STATE)),
        ("post", undo_url(ana), undo_post(ana, scope, **STATE)),
    ]


# --- 1. Access --------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
@pytest.mark.parametrize("who", ["anonymous", "deactivated"])
def test_filtered_requests_still_need_an_active_login(
    client, employee, data, who, headers
):
    if who == "deactivated":
        client.force_login(employee)
        employee.is_active = False
        employee.save()
    before = snapshot()

    for method, target, payload in state_requests(data):
        response = getattr(client, method)(target, payload, **headers)
        assert response.status_code == 302, (who, method, target)
        assert response.url.startswith("/accounts/login/")

    assert snapshot() == before


# --- 4, 12. Awkward search text and the search form -------------------------


def test_like_wildcards_in_search_are_literal(employee_client, data):
    for q in ("%", "_", "%doe", "d_e"):
        page = employee_client.get(url("all", q=q)).content.decode()
        assert order(page) == [], q
        assert "No matching applications." in page


def test_awkward_search_text_survives_every_link_and_form(employee_client, data):
    ana, scope = data["ana"], str(data["analyst"].pk)
    state = {"q": AWKWARD, "stage": "screening", "sort": "-updated"}
    before = snapshot()

    page = employee_client.get(url(scope, ana, **state)).content.decode()

    assert "<e>" not in page  # escaped, never markup
    assert unescape(attr(search_box(search_form(page)[1]), "value")) == AWKWARD
    links = [
        *sidebar_links(page),
        stage_link(page, S.OFFER),
        *sort_links(page).values(),
        *action_links(detail_panel(page)[1]).values(),
    ]
    for link in links:
        assert link_state(link)[1]["q"] == AWKWARD, link
    assert unescape(hidden(undo_form(detail_panel(page)[1])[1], "q")) == AWKWARD

    href = unescape(attr(action_links(detail_panel(page)[1])["interview"], "href"))
    modal = dialog(employee_client.get(href, **HTMX).content.decode())
    assert unescape(hidden(confirm_form(modal)[1], "q")) == AWKWARD
    assert snapshot() == before

    response = employee_client.post(
        move_url(ana), move_data(ana, S.INTERVIEW, scope, **state)
    )
    assert split(response["Location"])[1]["q"] == AWKWARD


def test_search_form_starts_a_new_selection_and_keeps_the_rest(employee_client, data):
    ana, scope = data["ana"], str(data["analyst"].pk)
    page = employee_client.get(url(scope, ana, **STATE)).content.decode()
    attrs, body = search_form(page)
    fields = form_fields(body)

    assert "application" not in fields  # approved: a new search clears it
    assert fields == {"opening": scope} | STATE
    fields["q"] = "  "  # a blank search clears only the search
    result = employee_client.get(attr(attrs, "action"), fields).content.decode()
    assert detail_panel(result) is None
    assert order(result) == pks(data, "ana", "ben", "fay")
    assert attr(sort_links(result)["updated"], "aria-current") == "true"
    assert attr(stage_link(result, S.SCREENING), "aria-current") == "true"


# --- 6, 17, 20. Counts, Archived, read-only ---------------------------------


def test_sidebar_counts_ignore_every_filter_and_gets_stay_read_only(
    employee_client, data
):
    analyst, designer = data["analyst"], data["designer"]
    states = [
        {},
        STATE,
        {"q": "ana"},
        {"stage": "hired"},
        {"sort": "-stage"},
        {"q": "nobody", "sort": "opening"},
    ]
    before = snapshot()

    for scope in ("all", str(analyst.pk), str(designer.pk)):
        for state in states:
            for headers in ({}, HTMX, RESTORE):
                response = employee_client.get(url(scope, **state), **headers)
                assert response.status_code == 200
                page = response.content.decode()
                # Ana, Ben and Fay are active (Hal is Hired); Cara is active.
                assert sidebar_count(page, analyst) == 3, (scope, state)
                assert sidebar_count(page, designer) == 1, (scope, state)
    for to in ("interview", "offer", "rejected", "withdrawn"):
        confirm = f"{move_url(data['ana'])}?to={to}&opening=all&{urlencode(STATE)}"
        for headers in ({}, HTMX):
            assert employee_client.get(confirm, **headers).status_code == 200

    assert snapshot() == before


@pytest.mark.parametrize("scope", ["all", "analyst"])
def test_archived_candidates_stay_listed_under_filters_and_after_a_move(
    employee_client, data, scope
):
    scope = "all" if scope == "all" else str(data["analyst"].pk)
    ana, fay = data["ana"], data["fay"]

    page = employee_client.get(url(scope, **STATE)).content.decode()
    assert ">Archived</span>" in dict(applicant_items(page))[fay.pk]

    response = employee_client.post(
        move_url(ana), move_data(ana, S.INTERVIEW, scope, **STATE), **HTMX
    )
    items = dict(applicant_items(response.content.decode()))
    assert fay.pk in items
    assert ">Archived</span>" in items[fay.pk]
    assert ana.pk not in items  # moved out of Screening


# --- 14, 15. All Openings scope through a move and Undo ---------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
@pytest.mark.parametrize("action", ["move", "undo"])
def test_all_openings_state_survives_a_move_and_undo(
    employee_client, data, action, headers
):
    ana = data["ana"]
    if action == "move":
        target, payload = move_url(ana), move_data(ana, S.INTERVIEW, "all", **STATE)
    else:
        target, payload = undo_url(ana), undo_post(ana, "all", **STATE)

    response = employee_client.post(target, payload, **headers)

    if headers:
        page = response.content.decode()
    else:
        assert split(response["Location"]) == (
            "/",
            {"opening": "all", "application": str(ana.pk)} | STATE,
        )
        page = employee_client.get(response["Location"]).content.decode()
    assert order(page) == pks(data, "ben", "fay", "cara")
    assert detail_panel(page)[0] == ana.pk
    [(level, _)] = alerts(oob(page, "messages") if headers else page)
    assert level == "alert-success"
    for link in sidebar_links(page):
        assert {k: v for k, v in link_state(link)[1].items() if k != "opening"} == (
            STATE
        )


# --- 16. Refused moves and Undo keep the state ------------------------------


def refused_requests(data, scope):
    ben, hal = data["ben"], data["hal"]
    return [
        # backward move, Hired is permanent, Undo with no recorded move
        (ben, move_url(ben), move_data(ben, S.APPLIED, scope, **STATE)),
        (hal, move_url(hal), move_data(hal, S.REJECTED, scope, **STATE)),
        (ben, undo_url(ben), undo_post(ben, scope, **STATE)),
        (hal, undo_url(hal), undo_post(hal, scope, **STATE)),
    ]


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_refused_moves_and_undos_keep_the_state_and_change_nothing(
    employee_client, data, headers
):
    scope = str(data["analyst"].pk)
    before = snapshot()

    for application, target, payload in refused_requests(data, scope):
        response = employee_client.post(target, payload, **headers)
        if headers:
            assert response.status_code == 200, target
            page = response.content.decode()
            [(level, _)] = alerts(oob(page, "messages"))
        else:
            assert response.status_code == 302, target
            assert split(response["Location"]) == (
                "/",
                {"opening": scope, "application": str(application.pk)} | STATE,
            )
            page = employee_client.get(response["Location"]).content.decode()
            [(level, _)] = alerts(page)
        assert level == "alert-error", target
        assert detail_panel(page)[0] == application.pk
        assert order(page) == pks(data, "ana", "ben", "fay")
        assert attr(search_box(search_form(page)[1]), "value") == "doe"
        assert attr(sort_links(page)["updated"], "aria-current") == "true"

    assert snapshot() == before


# --- 19. No duplicate containers --------------------------------------------


CONTAINERS = ('id="workspace"', 'id="modal"', 'id="messages"', 'id="workspace-search"')


def test_no_duplicate_containers_in_any_filtered_response(employee_client, data):
    ana, scope = data["ana"], str(data["analyst"].pk)
    state_page = url(scope, ana, **STATE)
    confirm = f"{move_url(ana)}?to=interview&opening={scope}&{urlencode(STATE)}"

    def counts(response):
        page = response.content.decode()
        return tuple(page.count(container) for container in CONTAINERS)

    get = employee_client.get
    assert counts(get(state_page)) == (1, 1, 1, 1)
    assert counts(get(state_page, **HTMX)) == (1, 0, 0, 1)
    assert counts(get(state_page, **RESTORE)) == (1, 1, 1, 1)
    assert counts(get(confirm)) == (0, 0, 1, 0)
    assert counts(get(confirm, **HTMX)) == (0, 0, 0, 0)

    moved = employee_client.post(
        move_url(ana), move_data(ana, S.INTERVIEW, scope, **STATE), **HTMX
    )
    assert counts(moved) == (1, 1, 1, 1)  # #modal and #messages out of band
    ana.refresh_from_db()
    undone = employee_client.post(
        undo_url(ana), undo_post(ana, scope, **STATE), follow=True
    )
    assert counts(undone) == (1, 1, 1, 1)
    assert len(re.findall(r'role="alert"', undone.content.decode())) == 1
