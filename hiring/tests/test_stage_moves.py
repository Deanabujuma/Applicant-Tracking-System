"""Phase 8 Test 3: confirmed stage moves through the hiring workspace."""

import datetime
import re
from html import unescape

import pytest
from django.test import Client
from django.utils import timezone
from django.utils.html import escape

from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import Application, Stage
from hiring.tests.test_workspace_detail import detail_panel
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


# --- Page readers -----------------------------------------------------------


def group(panel, group_id):
    """The data-move-to stages in one action group, in order (None if absent)."""
    found = re.findall(
        rf'<div\b[^>]*id="{group_id}"[^>]*>(.*?)</div>', panel, re.DOTALL
    )
    assert len(found) <= 1
    if not found:
        return None
    return re.findall(r'data-move-to="(\w+)"', found[0])


def action_links(panel):
    """{stage: attributes of its action link} for every action in the panel."""
    return {
        attr(tag, "data-move-to"): tag
        for tag in re.findall(r"<a\b([^>]*\bdata-move-to=[^>]*)>", panel)
    }


def dialog(page):
    found = re.findall(r"<dialog\b[^>]*>(.*?)</dialog>", page, re.DOTALL)
    assert len(found) == 1, "expected one confirmation dialog"
    return found[0]


def confirm_form(modal):
    """(attributes, body) of the dialog's POST form, or None."""
    found = re.findall(
        r'<form\b([^>]*method="post"[^>]*)>(.*?)</form>', modal, re.DOTALL
    )
    assert len(found) <= 1
    return found[0] if found else None


def hidden(form_body, name):
    match = re.search(rf'<input\b[^>]*name="{name}"[^>]*>', form_body)
    assert match, f"no {name} field"
    assert attr(match.group(0), "type") == "hidden"
    return attr(match.group(0), "value")


def alerts(page):
    return re.findall(r'<div role="alert" class="alert (alert-\w+)">(.*?)</div>', page)


def oob(page, element_id):
    """The inner HTML of an out-of-band swap element with this id."""
    match = re.search(
        rf'<div\b(?=[^>]*\bid="{element_id}")(?=[^>]*\bhx-swap-oob="true")[^>]*>',
        page,
    )
    assert match, f"no out-of-band #{element_id}"
    return page[match.end() :]


def sidebar_count(page, opening):
    item = re.search(
        rf'<li\b[^>]*data-opening="{opening.pk}"[^>]*>(.*?)</li>', page, re.DOTALL
    ).group(1)
    return int(re.search(r'title="Active applicants">\s*(\d+)\s*<', item).group(1))


# --- Data -------------------------------------------------------------------


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


@pytest.fixture
def analyst():
    return JobOpening.objects.create(title="Data Analyst", department="Finance")


@pytest.fixture
def make(employee, analyst):
    """Make an application in a stage, last changed long ago."""
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


def move_url(application):
    return f"/applications/{application.pk}/move/"


def confirm_url(application, to, scope="all"):
    return f"{move_url(application)}?to={to}&opening={scope}"


def post_data(to, expected, scope="all"):
    return {"to": to, "expected_stage": expected, "opening": scope}


# --- The panel's actions ----------------------------------------------------


@pytest.mark.parametrize("stage", list(Stage), ids=lambda s: s.value)
def test_panel_offers_exactly_the_allowed_moves_grouped(employee_client, make, stage):
    application = make(stage)
    before = snapshot()

    page = employee_client.get(
        f"/?opening=all&application={application.pk}"
    ).content.decode()
    _, panel = detail_panel(page)

    allowed = [str(s) for s in rules.allowed_moves(stage)]
    forward = [s for s in allowed if s not in rules.ENDINGS]
    ending = [s for s in allowed if s in rules.ENDINGS]
    if allowed:
        assert group(panel, "move-forward") == forward
        assert group(panel, "end-application") == ending
        assert "Move forward" in panel
        assert "End application" in panel
    else:  # Hired, Rejected, Withdrawn: no actions at all
        assert group(panel, "move-forward") is None
        assert group(panel, "end-application") is None
        assert "data-move-to" not in panel
    assert ("hired" in allowed) is (stage == S.OFFER)  # only Offer can hire

    # Each action fetches its confirmation; none can change anything itself.
    for to, link in action_links(panel).items():
        url = confirm_url(application, to)
        assert unescape(attr(link, "href")) == url
        assert unescape(attr(link, "hx-get")) == url
        assert attr(link, "hx-target") == "#modal"
    for forbidden in ("<form", "<button", "hx-post", "Undo"):
        assert forbidden not in panel
    assert snapshot() == before


# --- The confirmation -------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "to", "must_say", "must_not_say"),
    [
        (S.APPLIED, S.SCREENING, ["Move forward", "Applied", "Screening"], ["skip"]),
        (
            S.APPLIED,
            S.OFFER,
            ["Skip ahead", "Screening", "Interview", "Final Review", "skipped"],
            [],
        ),
        (S.INTERVIEW, S.REJECTED, ["Rejected", "undo this once"], ["skip"]),
        (S.SCREENING, S.WITHDRAWN, ["Withdrawn", "undo this once"], ["skip"]),
        (
            S.OFFER,
            S.HIRED,
            ["Hired", "Data Analyst", "permanent", "cannot be undone"],
            [],
        ),
    ],
    ids=["advance", "skip", "reject", "withdraw", "hire"],
)
def test_confirmation_wording_and_expected_stage(
    employee_client, make, start, to, must_say, must_not_say
):
    application = make(start)
    before = snapshot()

    for headers in (HTMX, {}):
        response = employee_client.get(confirm_url(application, to), **headers)
        assert response.status_code == 200
        page = response.content.decode()
        assert ("<html" in page) is (not headers)  # modal fragment or full page
        modal = dialog(page)

        assert str(application.candidate) in modal
        for words in must_say:
            assert words.lower() in modal.lower(), words
        for words in must_not_say:
            assert words.lower() not in modal.lower(), words
        is_hire, is_end = to == S.HIRED, to in rules.ENDINGS
        assert ("permanent" in modal) is is_hire
        assert ("undo this once" in modal) is is_end

        # Confirm POSTs the move with the stage this employee saw.
        attrs, body = confirm_form(modal)
        assert attr(attrs, "action") == move_url(application)
        assert attr(attrs, "hx-post") == move_url(application)
        assert attr(attrs, "hx-target") == "#workspace"
        assert attr(attrs, "hx-swap") == "outerHTML"
        assert "csrfmiddlewaretoken" in body
        assert hidden(body, "to") == to
        assert hidden(body, "expected_stage") == start
        assert hidden(body, "opening") == "all"

        # Cancel just closes the dialog: no request, no change.
        assert re.search(
            r'<form\b[^>]*method="dialog"[^>]*>\s*<button\b[^>]*>Cancel</button>', modal
        )
        if not headers:  # the full page also links back to the selection
            back = f"/?opening=all&amp;application={application.pk}"
            assert f'href="{back}"' in page

    assert snapshot() == before


def test_confirmation_for_a_move_no_longer_allowed_offers_only_cancel(
    employee_client, make
):
    """An old action link, opened after someone hired the applicant."""
    application = make(S.HIRED)
    before = snapshot()

    for headers in (HTMX, {}):
        response = employee_client.get(confirm_url(application, S.INTERVIEW), **headers)
        assert response.status_code == 200
        modal = dialog(response.content.decode())
        assert escape(rules.why_not(S.HIRED, S.INTERVIEW)) in modal
        assert confirm_form(modal) is None
        assert 'method="dialog"' in modal

    assert snapshot() == before


# --- Confirming -------------------------------------------------------------


def test_confirmed_htmx_post_moves_and_refreshes_the_workspace(
    employee_client, employee, make, analyst
):
    application = make(S.OFFER)
    make(S.SCREENING)  # another active applicant on the same opening
    scope = str(analyst.pk)
    page = employee_client.get(
        f"/?opening={scope}&application={application.pk}"
    ).content.decode()
    assert sidebar_count(page, analyst) == 2

    response = employee_client.post(
        move_url(application), post_data(S.HIRED, S.OFFER, scope), **HTMX
    )

    assert response.status_code == 200
    page = response.content.decode()
    application.refresh_from_db()
    assert (application.stage, application.previous_stage) == (S.HIRED, S.OFFER)
    assert application.stage_changed_by == employee

    # The whole workspace, same scope and selection, showing the new stage.
    assert page.strip().startswith('<div id="workspace"')
    assert "<html" not in page
    assert current_hrefs(page) == [f"/?opening={scope}"]
    assert sidebar_count(page, analyst) == 1  # Hired isn't active
    summary = stage_summary(page)
    assert summary[S.OFFER.value][1] == 0
    assert summary[S.HIRED.value][1] == 1
    assert total(page) == 2
    pk, panel = detail_panel(page)
    assert pk == application.pk
    assert "Hired" in panel
    assert "data-move-to" not in panel  # Hired: no further moves

    # The modal is cleared and a success message shown, out of band.
    assert re.match(r"\s*</div>", oob(page, "modal"))
    [(kind, text)] = alerts(oob(page, "messages"))
    assert kind == "alert-success"
    assert str(application.candidate) in text
    assert "Hired" in text


def test_non_htmx_post_redirects_to_the_same_selection(employee_client, make):
    application = make(S.APPLIED)

    response = employee_client.post(
        move_url(application), post_data(S.INTERVIEW, S.APPLIED), follow=True
    )

    selection = f"/?opening=all&application={application.pk}"
    assert response.redirect_chain == [(selection, 302)]
    assert Application.objects.get(pk=application.pk).stage == S.INTERVIEW
    page = response.content.decode()
    [(kind, text)] = alerts(page)
    assert kind == "alert-success"
    assert "Interview" in text
    assert detail_panel(page)[0] == application.pk
    assert alerts(employee_client.get(selection).content.decode()) == []  # once


def stale_setup(make, employee):
    """Opened at Applied; another employee then moved it to Screening."""
    application = make(S.APPLIED)
    Application.objects.get(pk=application.pk).move_to(
        S.SCREENING, employee, expected_stage=S.APPLIED
    )
    return application, post_data(S.INTERVIEW, S.APPLIED)  # valid from Screening


@pytest.mark.parametrize(
    "case", ["stale", "backward", "hire-too-early", "unknown-stage", "lying-expected"]
)
@pytest.mark.parametrize("headers", [HTMX, {}], ids=["htmx", "page"])
def test_rejected_posts_change_nothing_and_explain(
    employee_client, employee, make, case, headers
):
    if case == "stale":
        application, data = stale_setup(make, employee)
    else:
        application = make(S.SCREENING)
        data = {
            "backward": post_data(S.APPLIED, S.SCREENING),
            "hire-too-early": post_data(S.HIRED, S.SCREENING),
            "unknown-stage": post_data("promoted", S.SCREENING),
            # Claims Offer so Hired would look valid; the stored stage wins.
            "lying-expected": post_data(S.HIRED, S.OFFER),
        }[case]
    before = snapshot()

    response = employee_client.post(move_url(application), data, **headers)

    assert snapshot() == before
    current = Application.objects.get(pk=application.pk)
    if headers:
        assert response.status_code == 200
        page = response.content.decode()
        # The refreshed workspace shows where the application really is.
        assert page.strip().startswith('<div id="workspace"')
        pk, panel = detail_panel(page)
        assert pk == application.pk
        assert current.get_stage_display() in panel
        assert re.match(r"\s*</div>", oob(page, "modal"))
        [(kind, text)] = alerts(oob(page, "messages"))
    else:
        assert response.status_code == 302
        assert response.url == f"/?opening=all&application={application.pk}"
        [(kind, text)] = alerts(employee_client.get(response.url).content.decode())
    assert kind == "alert-error"
    assert text.strip()
    if case in ("stale", "lying-expected"):
        assert "changed to" in unescape(text)


def test_forged_application_scope_or_fields_are_refused(employee_client, make, analyst):
    application = make(S.APPLIED)
    designer = JobOpening.objects.create(title="Designer", department="Art")
    missing = Application.objects.order_by("-pk").first().pk + 1
    before = snapshot()

    for headers in (HTMX, {}):
        # No such application.
        assert (
            employee_client.post(
                f"/applications/{missing}/move/",
                post_data(S.SCREENING, S.APPLIED),
                **headers,
            ).status_code
            == 404
        )
        # A scope the application isn't in.
        assert (
            employee_client.post(
                move_url(application),
                post_data(S.SCREENING, S.APPLIED, str(designer.pk)),
                **headers,
            ).status_code
            == 404
        )
        # Missing fields.
        for drop in ("to", "expected_stage"):
            data = post_data(S.SCREENING, S.APPLIED)
            del data[drop]
            response = employee_client.post(move_url(application), data, **headers)
            assert response.status_code == 400, drop
        # Confirmation for a scope it isn't in, or an unknown stage.
        get = employee_client.get
        bad_scope = confirm_url(application, S.SCREENING, str(designer.pk))
        assert get(bad_scope, **headers).status_code == 404
        assert get(confirm_url(application, "promoted"), **headers).status_code == 400

    assert snapshot() == before


def test_moves_need_login_and_csrf(client, employee, make):
    application = make(S.APPLIED)
    before = snapshot()

    for method in ("get", "post"):
        response = getattr(client, method)(confirm_url(application, S.SCREENING))
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(employee)
    response = csrf_client.post(
        move_url(application), post_data(S.SCREENING, S.APPLIED), **HTMX
    )
    assert response.status_code == 403
    assert snapshot() == before

    modal = csrf_client.get(
        confirm_url(application, S.SCREENING), **HTMX
    ).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', modal).group(1)
    response = csrf_client.post(
        move_url(application),
        {**post_data(S.SCREENING, S.APPLIED), "csrfmiddlewaretoken": token},
        **HTMX,
    )
    assert response.status_code == 200
    assert Application.objects.get(pk=application.pk).stage == S.SCREENING
