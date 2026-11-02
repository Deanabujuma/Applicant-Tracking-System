"""Phase 10 Test 3: the workspace keeps its filter state (opening, q, stage,
sort) through navigation, search, stage moves and Undo."""

import datetime
import re
from html import unescape
from urllib.parse import parse_qs

import pytest
from django.test import Client
from django.utils import timezone

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
from hiring.tests.test_workspace_filters import all_stages_link, counts, stage_link
from hiring.tests.test_workspace_selection import (
    HTMX,
    applicant_items,
    attr,
    current_hrefs,
    sidebar_links,
)
from hiring.tests.test_workspace_sorting import sort_links
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

S = Stage
RESTORE = {**HTMX, "HTTP_HX_HISTORY_RESTORE_REQUEST": "true"}
LONG_AGO = timezone.now() - datetime.timedelta(days=10)
# A search, a stage filter and a non-default sort, all at once.
STATE = {"q": "doe", "stage": "screening", "sort": "-updated"}
BAD_STATE = [
    {"q": "x" * 101},
    {"stage": "bogus"},
    {"sort": "bogus"},
    {"sort": "--name"},
]


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
    """Under STATE, Data Analyst lists Ana then Ben (oldest change first).

    Dev doesn't match the search and Eve isn't in Screening; Cara is the
    Designer's only match. Ana's last move (Applied → Screening) can be undone.
    """
    analyst = JobOpening.objects.create(title="Data Analyst", department="Finance")
    designer = JobOpening.objects.create(title="Designer", department="Art")
    rows = {
        # name: (first, last, opening, stage, previous, days after LONG_AGO)
        "ana": ("Ana", "Doe", analyst, S.SCREENING, S.APPLIED, 1),
        "ben": ("Ben", "Doe", analyst, S.SCREENING, None, 2),
        "dev": ("Dev", "Smith", analyst, S.SCREENING, None, 3),
        "eve": ("Eve", "Doe", analyst, S.APPLIED, None, 4),
        "cara": ("Cara", "Doe", designer, S.SCREENING, None, 5),
    }
    made = {"analyst": analyst, "designer": designer}
    for name, (first, last, opening, stage, previous, days) in rows.items():
        application = Application.objects.create(
            candidate=Candidate.objects.create(
                first_name=first,
                last_name=last,
                email=f"{name}@example.com",
                source=Source.REFERRAL,
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


# --- Readers ----------------------------------------------------------------


def snapshot():
    return (
        list(Application.objects.order_by("pk").values()),
        list(Candidate.objects.order_by("pk").values()),
        list(JobOpening.objects.order_by("pk").values()),
    )


def split(href):
    """(path, {name: value}) of a link; blank values are kept, so a link
    that sends an empty parameter doesn't match one that omits it."""
    path, _, query = unescape(href).partition("?")
    params = parse_qs(query, keep_blank_values=True)
    assert all(len(values) == 1 for values in params.values()), href
    return path, {name: values[0] for name, values in params.items()}


def link_state(link):
    """(path, params) of a link's href, checking hx-get is the same URL."""
    assert unescape(attr(link, "hx-get")) == unescape(attr(link, "href"))
    return split(attr(link, "href"))


def state_url(scope, application=None, **state):
    params = {"opening": scope}
    if application is not None:
        params["application"] = application.pk
    params |= {name: value for name, value in state.items() if value}
    return "/?" + "&".join(f"{name}={value}" for name, value in params.items())


def order(page):
    return [pk for pk, _ in applicant_items(page)]


def pks(data, *names):
    return [data[name].pk for name in names]


def search_form(page):
    """(attributes, body) of the one #workspace-search form."""
    found = re.findall(
        r'<form\b([^>]*\bid="workspace-search"[^>]*)>(.*?)</form>', page, re.DOTALL
    )
    assert len(found) == 1, "expected one #workspace-search form"
    return found[0]


def search_box(form_body):
    match = re.search(r'<input\b[^>]*\bname="q"[^>]*>', form_body)
    assert match, "no q field in the search form"
    return match.group(0)


def form_fields(form_body):
    """{name: value} of every named input in a form."""
    return {
        attr(tag, "name"): unescape(attr(tag, "value") or "")
        for tag in re.findall(r"<input\b[^>]*>", form_body)
        if attr(tag, "name")
    }


def scope_of(data, opening):
    return str(data[opening].pk)


def move_data(application, to, scope, *, expected=None, **state):
    return {
        "to": to,
        "expected_stage": expected or application.stage,
        "expected_changed_at": application.stage_changed_at.isoformat(),
        "opening": scope,
        **state,
    }


def undo_post(application, scope, *, changed_at=None, **state):
    return {
        "expected_stage": application.stage,
        "expected_changed_at": (changed_at or application.stage_changed_at).isoformat(),
        "opening": scope,
        **state,
    }


def assert_filtered_view(page, data, *, selected):
    """The analyst view under STATE: Ben only (Ana has left Screening or the
    list), the panel still on ``selected``, and every control still filtered."""
    scope = scope_of(data, "analyst")
    assert order(page) == pks(data, "ben")
    assert detail_panel(page)[0] == selected.pk
    assert attr(stage_link(page, S.SCREENING), "aria-current") == "true"
    assert attr(sort_links(page)["updated"], "aria-current") == "true"
    assert attr(search_box(search_form(page)[1]), "value") == "doe"
    _, row = link_state(sort_links(page)["name"])
    assert row == {"opening": scope, "application": str(selected.pk)} | STATE | {
        "sort": "name"
    }


# --- Navigation links -------------------------------------------------------


def test_sidebar_links_keep_the_filters_but_drop_the_selection(employee_client, data):
    scope = scope_of(data, "analyst")
    page = employee_client.get(state_url(scope, data["ana"], **STATE)).content.decode()

    found = [link_state(link) for link in sidebar_links(page)]

    assert found == [
        ("/", {"opening": "all"} | STATE),
        ("/", {"opening": scope} | STATE),
        ("/", {"opening": scope_of(data, "designer")} | STATE),
    ]
    assert len(current_hrefs(page)) == 1  # still only Data Analyst is current
    assert split(current_hrefs(page)[0])[1]["opening"] == scope


def test_stage_links_change_only_the_stage(employee_client, data):
    scope = scope_of(data, "analyst")
    page = employee_client.get(state_url(scope, data["ana"], **STATE)).content.decode()
    kept = {"opening": scope, "q": "doe", "sort": "-updated"}

    for stage in Stage:
        assert link_state(stage_link(page, stage)) == (
            "/",
            kept | {"stage": stage.value},
        )
    assert link_state(all_stages_link(page)) == ("/", kept)  # clears only stage


def test_sort_links_keep_the_filters_and_the_selection(employee_client, data):
    scope = scope_of(data, "analyst")
    page = employee_client.get(state_url(scope, data["ana"], **STATE)).content.decode()

    _, params = link_state(sort_links(page)["updated"])

    assert params == {"opening": scope, "application": str(data["ana"].pk)} | STATE | {
        "sort": "updated"
    }


def test_applicant_rows_select_within_the_filters(employee_client, data):
    scope = scope_of(data, "analyst")
    page = employee_client.get(state_url(scope, **STATE)).content.decode()

    rows = dict(applicant_items(page))

    assert list(rows) == pks(data, "ana", "ben")
    for pk, item in rows.items():
        link = re.search(r"<a\b([^>]*)>", item).group(1)
        assert link_state(link) == (
            "/",
            {"opening": scope, "application": str(pk)} | STATE,
        )


def test_links_without_filters_stay_as_they_were(employee_client, data):
    scope = scope_of(data, "analyst")
    page = employee_client.get(f"/?opening={scope}").content.decode()

    assert link_state(sidebar_links(page)[0]) == ("/", {"opening": "all"})
    assert link_state(stage_link(page, S.APPLIED)) == (
        "/",
        {"opening": scope, "stage": "applied"},
    )
    row = re.search(r"<a\b([^>]*)>", applicant_items(page)[0][1]).group(1)
    assert link_state(row)[1] == {
        "opening": scope,
        "application": str(applicant_items(page)[0][0]),
    }


# --- The search form --------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_search_form_is_a_get_form_carrying_the_state(employee_client, data, headers):
    scope = scope_of(data, "analyst")
    page = employee_client.get(
        state_url(scope, data["ana"], **STATE), **headers
    ).content.decode()

    attrs, body = search_form(page)

    assert attr(attrs, "method") == "get"
    assert attr(attrs, "action") == "/"
    assert attr(attrs, "hx-get") == "/"
    assert attr(attrs, "hx-target") == "#workspace"
    assert attr(attrs, "hx-swap") == "outerHTML"
    assert attr(attrs, "hx-push-url") == "true"
    trigger = attr(attrs, "hx-trigger") or ""
    assert "submit" in trigger
    assert re.search(r"\bdelay:\d+m?s\b", trigger), trigger  # shortly after typing
    box = search_box(body)
    assert attr(box, "value") == "doe"
    assert attr(box, "type") == "search"
    assert hidden(body, "opening") == scope
    assert hidden(body, "stage") == "screening"
    assert hidden(body, "sort") == "-updated"
    # A plain GET: no CSRF token, nothing that posts, nothing nested.
    assert "csrfmiddlewaretoken" not in body
    assert "hx-post" not in attrs
    assert "<form" not in body
    assert "workspace-search" not in detail_panel(page)[1]


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_submitting_the_search_form_reproduces_the_filters(
    employee_client, data, headers
):
    scope = scope_of(data, "analyst")
    page = employee_client.get(state_url(scope, **STATE)).content.decode()
    attrs, body = search_form(page)
    fields = form_fields(body)
    before = snapshot()

    response = employee_client.get(attr(attrs, "action"), fields, **headers)

    assert response.status_code == 200
    assert order(response.content.decode()) == pks(data, "ana", "ben")
    # Changing only the search text keeps the opening, stage and sort.
    fields["q"] = "ben"
    changed = employee_client.get("/", fields, **headers).content.decode()
    assert order(changed) == pks(data, "ben")
    assert attr(sort_links(changed)["updated"], "aria-current") == "true"
    assert snapshot() == before


def test_search_form_without_filters(employee_client, data):
    page = employee_client.get("/").content.decode()

    _, body = search_form(page)

    assert attr(search_box(body), "value") in (None, "")
    assert hidden(body, "opening") == "all"


@pytest.mark.parametrize(
    "headers", [{}, HTMX, RESTORE], ids=["page", "htmx", "restore"]
)
def test_a_state_url_reproduces_the_same_view(employee_client, data, headers):
    scope = scope_of(data, "analyst")
    before = snapshot()

    response = employee_client.get(state_url(scope, data["ben"], **STATE), **headers)

    assert response.status_code == 200
    page = response.content.decode()
    assert ("<html" in page) is (headers is not HTMX)
    assert page.count('id="workspace"') == 1
    assert order(page) == pks(data, "ana", "ben")
    assert detail_panel(page)[0] == data["ben"].pk
    assert split(current_hrefs(page)[0])[1]["opening"] == scope
    assert attr(stage_link(page, S.SCREENING), "aria-current") == "true"
    assert attr(sort_links(page)["updated"], "aria-current") == "true"
    assert attr(search_box(search_form(page)[1]), "value") == "doe"
    assert snapshot() == before


@pytest.mark.parametrize("bad", BAD_STATE, ids=["q", "stage", "sort", "double-minus"])
def test_bad_state_values_are_still_400_with_everything_else(
    employee_client, data, bad
):
    scope = scope_of(data, "analyst")
    for headers in ({}, HTMX):
        url = state_url(scope, data["ana"], **(STATE | bad))
        assert employee_client.get(url, **headers).status_code == 400


# --- Stage moves ------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_move_links_and_confirmations_carry_the_state(employee_client, data, headers):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    page = employee_client.get(state_url(scope, ana, **STATE)).content.decode()
    links = action_links(detail_panel(page)[1])
    before = snapshot()

    for to, link in links.items():
        path, params = link_state(link)
        assert path == f"/applications/{ana.pk}/move/"
        assert params == {"to": to, "opening": scope} | STATE

        confirmation = employee_client.get(unescape(attr(link, "href")), **headers)
        assert confirmation.status_code == 200
        body = confirmation.content.decode()
        _, form = confirm_form(dialog(body))
        assert hidden(form, "opening") == scope
        for name, value in STATE.items():
            assert hidden(form, name) == value, (to, name)
        if not headers:  # the full confirmation page links back to the same view
            back = re.search(
                r"<a\b([^>]*)>\s*Back to the workspace\s*</a>", body
            ).group(1)
            assert split(attr(back, "href")) == (
                "/",
                {"opening": scope, "application": str(ana.pk)} | STATE,
            )
    assert snapshot() == before


@pytest.mark.parametrize("bad", BAD_STATE, ids=["q", "stage", "sort", "double-minus"])
def test_bad_state_values_are_400_for_move_confirmations(employee_client, data, bad):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    query = "&".join(f"{k}={v}" for k, v in (STATE | bad).items())
    for headers in ({}, HTMX):
        url = f"/applications/{ana.pk}/move/?to=interview&opening={scope}&{query}"
        assert employee_client.get(url, **headers).status_code == 400


def test_htmx_move_keeps_the_filters_and_the_selection(employee_client, data):
    scope, ana = scope_of(data, "analyst"), data["ana"]

    response = employee_client.post(
        f"/applications/{ana.pk}/move/",
        move_data(ana, S.INTERVIEW, scope, **STATE),
        **HTMX,
    )

    assert response.status_code == 200
    page = response.content.decode()
    ana.refresh_from_db()
    assert ana.stage == S.INTERVIEW
    # Ana left Screening: off the filtered list, still in the panel.
    assert_filtered_view(page, data, selected=ana)
    # Counts follow the opening and the search; the sidebar ignores filters.
    assert counts(page)["screening"] == 1
    assert counts(page)["interview"] == 1
    assert counts(page)["applied"] == 1
    assert sidebar_count(page, data["analyst"]) == 4
    [(level, _)] = alerts(oob(page, "messages"))
    assert level == "alert-success"


def test_normal_move_redirects_to_the_same_filtered_view(employee_client, data):
    scope, ana = scope_of(data, "analyst"), data["ana"]

    response = employee_client.post(
        f"/applications/{ana.pk}/move/", move_data(ana, S.INTERVIEW, scope, **STATE)
    )

    assert response.status_code == 302
    assert split(response["Location"]) == (
        "/",
        {"opening": scope, "application": str(ana.pk)} | STATE,
    )
    page = employee_client.get(response["Location"]).content.decode()
    ana.refresh_from_db()
    assert_filtered_view(page, data, selected=ana)


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_a_refused_move_keeps_the_filters_and_changes_nothing(
    employee_client, data, headers
):
    scope, ben = scope_of(data, "analyst"), data["ben"]
    before = snapshot()

    response = employee_client.post(
        f"/applications/{ben.pk}/move/",
        move_data(ben, S.INTERVIEW, scope, expected=S.APPLIED, **STATE),  # stale
        **headers,
    )

    assert snapshot() == before
    if headers:
        page = response.content.decode()
        [(level, _)] = alerts(oob(page, "messages"))
        assert level == "alert-error"
    else:
        assert response.status_code == 302
        assert split(response["Location"]) == (
            "/",
            {"opening": scope, "application": str(ben.pk)} | STATE,
        )
        page = employee_client.get(response["Location"]).content.decode()
    assert order(page) == pks(data, "ana", "ben")
    assert detail_panel(page)[0] == ben.pk
    assert attr(stage_link(page, S.SCREENING), "aria-current") == "true"
    assert attr(sort_links(page)["updated"], "aria-current") == "true"


@pytest.mark.parametrize("bad", BAD_STATE, ids=["q", "stage", "sort", "double-minus"])
def test_bad_state_values_are_400_for_moves_and_undo(employee_client, data, bad):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    before = snapshot()
    for headers in ({}, HTMX):
        move = employee_client.post(
            f"/applications/{ana.pk}/move/",
            move_data(ana, S.INTERVIEW, scope, **(STATE | bad)),
            **headers,
        )
        undo = employee_client.post(
            f"/applications/{ana.pk}/undo/",
            undo_post(ana, scope, **(STATE | bad)),
            **headers,
        )
        assert (move.status_code, undo.status_code) == (400, 400)
    assert snapshot() == before


# --- Undo -------------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_undo_form_carries_the_state(employee_client, data, headers):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    page = employee_client.get(
        state_url(scope, ana, **STATE), **headers
    ).content.decode()

    _, body = undo_form(detail_panel(page)[1])

    assert hidden(body, "opening") == scope
    for name, value in STATE.items():
        assert hidden(body, name) == value, name


def test_htmx_undo_keeps_the_filters_and_the_selection(employee_client, data):
    scope, ana = scope_of(data, "analyst"), data["ana"]

    response = employee_client.post(
        f"/applications/{ana.pk}/undo/", undo_post(ana, scope, **STATE), **HTMX
    )

    assert response.status_code == 200
    page = response.content.decode()
    ana.refresh_from_db()
    assert ana.stage == S.APPLIED
    assert_filtered_view(page, data, selected=ana)  # back in Applied: off the list
    assert counts(page)["applied"] == 2
    assert sidebar_count(page, data["analyst"]) == 4
    [(level, _)] = alerts(oob(page, "messages"))
    assert level == "alert-success"


def test_normal_undo_redirects_to_the_same_filtered_view(employee_client, data):
    scope, ana = scope_of(data, "analyst"), data["ana"]

    response = employee_client.post(
        f"/applications/{ana.pk}/undo/", undo_post(ana, scope, **STATE)
    )

    assert response.status_code == 302
    assert split(response["Location"]) == (
        "/",
        {"opening": scope, "application": str(ana.pk)} | STATE,
    )
    page = employee_client.get(response["Location"]).content.decode()
    ana.refresh_from_db()
    assert_filtered_view(page, data, selected=ana)


@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_a_refused_undo_keeps_the_filters_and_changes_nothing(
    employee_client, data, headers
):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    before = snapshot()

    response = employee_client.post(
        f"/applications/{ana.pk}/undo/",
        undo_post(ana, scope, changed_at=LONG_AGO, **STATE),  # stale timestamp
        **headers,
    )

    assert snapshot() == before
    if headers:
        page = response.content.decode()
        [(level, _)] = alerts(oob(page, "messages"))
        assert level == "alert-error"
    else:
        assert response.status_code == 302
        assert split(response["Location"]) == (
            "/",
            {"opening": scope, "application": str(ana.pk)} | STATE,
        )
        page = employee_client.get(response["Location"]).content.decode()
    assert order(page) == pks(data, "ana", "ben")
    assert detail_panel(page)[0] == ana.pk
    assert attr(search_box(search_form(page)[1]), "value") == "doe"


# --- Protections kept -------------------------------------------------------


def test_state_doesnt_bypass_login_or_csrf(employee, data):
    scope, ana = scope_of(data, "analyst"), data["ana"]
    before = snapshot()

    anonymous = Client()
    response = anonymous.get(state_url(scope, ana, **STATE))
    assert response.status_code == 302
    assert "/login/" in response["Location"]

    strict = Client(enforce_csrf_checks=True)
    strict.force_login(employee)
    for url, payload in (
        (f"/applications/{ana.pk}/move/", move_data(ana, S.INTERVIEW, scope, **STATE)),
        (f"/applications/{ana.pk}/undo/", undo_post(ana, scope, **STATE)),
    ):
        for headers in ({}, HTMX):
            assert strict.post(url, payload, **headers).status_code == 403
    assert snapshot() == before
