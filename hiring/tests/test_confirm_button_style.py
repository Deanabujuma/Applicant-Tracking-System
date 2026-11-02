"""Confirm button colour by move kind: every skip is red (btn-error)."""

import re

import pytest

from candidates.models import Candidate, Source
from hiring import rules
from hiring.models import Application, Stage
from hiring.tests.test_stage_moves import confirm_form, confirm_url, dialog
from hiring.tests.test_workspace_selection import HTMX
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="jsmith"))
    return client


@pytest.fixture
def make(django_user_model):
    def make_application(stage):
        return Application.objects.create(
            candidate=Candidate.objects.create(
                first_name="Ana",
                last_name="Doe",
                email="ana@example.com",
                source=Source.REFERRAL,
            ),
            opening=JobOpening.objects.create(title="Data Analyst", department="IT"),
            stage=stage,
            stage_changed_by=django_user_model.objects.create_user(username="maker"),
        )

    return make_application


PAIRS = [
    (from_stage, to_stage)
    for from_stage in Stage
    for to_stage in rules.allowed_moves(from_stage)
]
EXPECTED_CLASS = {
    "advance": "btn-primary",
    "skip": "btn-error",
    "end": "btn-error",
    "hire": "btn-success",
}


def confirm_button_classes(modal):
    _, body = confirm_form(modal)
    match = re.search(
        r'<button\b[^>]*class="([^"]*)"[^>]*>\s*Confirm\s*</button>', body
    )
    assert match, "no Confirm button"
    return match.group(1).split()


@pytest.mark.parametrize(
    ("from_stage", "to_stage"),
    PAIRS,
    ids=[f"{a.value}-{b}" for a, b in PAIRS],
)
@pytest.mark.parametrize("headers", [{}, HTMX], ids=["page", "htmx"])
def test_confirm_button_colour_matches_the_kind_of_move(
    employee_client, make, from_stage, to_stage, headers
):
    application = make(from_stage)
    kind = rules.kind_of(from_stage, to_stage)

    page = employee_client.get(confirm_url(application, to_stage), **headers)
    classes = confirm_button_classes(dialog(page.content.decode()))

    assert "btn" in classes
    assert EXPECTED_CLASS[kind] in classes, (kind, classes)
    if kind == "skip":
        assert "btn-primary" not in classes  # no longer purple
    if kind == "advance":
        assert "btn-error" not in classes  # ordinary moves stay as they were
