"""Phase 5 Test 2: one shared application form, two entry points, strict eligibility."""

import re
from dataclasses import dataclass

import pytest
from django.utils import timezone

from candidates.models import Candidate, Source
from hiring.models import Application, Stage
from openings.models import JobOpening, OpeningStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee(django_user_model):
    return django_user_model.objects.create_user(username="jsmith")


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee)
    return client


def make_candidate(first, *, archived=False):
    return Candidate.objects.create(
        first_name=first,
        last_name="Doe",
        email=f"{first.lower()}@example.com",
        source=Source.REFERRAL,
        is_archived=archived,
    )


@pytest.fixture
def records(employee):
    """Jane and Bob are active, Ann is archived; Analyst and Backend are Open,
    Legacy is Closed. Bob has already applied to Analyst."""
    r = {
        "jane": make_candidate("Jane"),
        "bob": make_candidate("Bob"),
        "ann": make_candidate("Ann", archived=True),
        "analyst": JobOpening.objects.create(title="Data Analyst", department="Fin"),
        "backend": JobOpening.objects.create(title="Backend Dev", department="IT"),
        "legacy": JobOpening.objects.create(
            title="Legacy Role", department="IT", status=OpeningStatus.CLOSED
        ),
    }
    Application.objects.create(
        candidate=r["bob"], opening=r["analyst"], stage_changed_by=employee
    )
    return r


@dataclass
class Entry:
    """One way into the shared form: one side fixed by the URL, the other chosen."""

    fixed: str  # "candidate" or "opening": the side given in the URL
    chosen: str  # the form field the employee picks
    detail_url: str  # where the entry link lives, and where success returns
    fixed_key: str  # the eligible fixed record
    eligible_choices: set  # keys of the only choices that may be offered
    valid_choice: str
    rejected_choices: dict  # key -> why it must be rejected on submit
    ineligible_fixed_key: str  # a fixed record that must not receive applications
    forged_fixed_key: str  # a different record forged in POST for the fixed side


ENTRIES = {
    "from_candidate": Entry(
        fixed="candidate",
        chosen="opening",
        detail_url="/candidates/{pk}/",
        fixed_key="bob",
        eligible_choices={
            "backend"
        },  # Legacy is Closed; Bob already applied to Analyst
        valid_choice="backend",
        rejected_choices={"legacy": "closed opening", "analyst": "duplicate pair"},
        ineligible_fixed_key="ann",  # archived
        forged_fixed_key="jane",
    ),
    "from_opening": Entry(
        fixed="opening",
        chosen="candidate",
        detail_url="/openings/{pk}/",
        fixed_key="analyst",
        eligible_choices={"jane"},  # Ann is archived; Bob already applied
        valid_choice="jane",
        rejected_choices={"ann": "archived candidate", "bob": "duplicate pair"},
        ineligible_fixed_key="legacy",  # Closed
        forged_fixed_key="backend",
    ),
}


def form_url(entry, record):
    return f"/applications/new/?{entry.fixed}={record.pk}"


def offered_ids(page, field):
    match = re.search(rf'<select name="{field}"[^>]*>(.*?)</select>', page, re.DOTALL)
    assert match, f"no {field} dropdown"
    return {int(pk) for pk in re.findall(r'<option value="(\d+)"', match.group(1))}


@pytest.mark.parametrize("entry_name", ENTRIES)
def test_shared_application_form_enforces_eligibility(
    employee_client, employee, django_user_model, records, entry_name
):
    entry = ENTRIES[entry_name]
    fixed = records[entry.fixed_key]
    url = form_url(entry, fixed)
    count = Application.objects.count()  # 1: Bob -> Analyst

    # The fixed record's detail page links to the shared form.
    detail = employee_client.get(entry.detail_url.format(pk=fixed.pk)).content.decode()
    assert f'href="{url}"' in detail

    # Both entry points use the same form class.
    response = employee_client.get(url)
    assert response.status_code == 200
    other = next(e for e in ENTRIES.values() if e is not entry)
    other_form = employee_client.get(form_url(other, records[other.fixed_key])).context[
        "form"
    ]
    assert type(response.context["form"]) is type(other_form)

    # Only eligible choices are offered, and no stage fields are on the form.
    page = response.content.decode()
    assert offered_ids(page, entry.chosen) == {
        records[k].pk for k in entry.eligible_choices
    }
    for field in ("stage", "previous_stage", "stage_changed_by", "stage_changed_at"):
        assert f'name="{field}"' not in page

    # Ineligible choices are rejected on submit (even though they aren't offered).
    for key, reason in entry.rejected_choices.items():
        response = employee_client.post(url, {entry.chosen: records[key].pk})
        assert response.status_code == 200, reason
        assert response.context["form"].errors, reason
        assert Application.objects.count() == count, reason

    # An ineligible fixed record (archived candidate / Closed opening) gets nothing.
    bad_url = form_url(entry, records[entry.ineligible_fixed_key])
    response = employee_client.post(
        bad_url, {entry.chosen: records[entry.valid_choice].pk}
    )
    assert response.status_code != 302
    assert Application.objects.count() == count

    # A valid submission with forged extra fields: the URL's fixed record wins,
    # and the application controls every stage field.
    someone_else = django_user_model.objects.create_user(username="intruder")
    started = timezone.now()
    response = employee_client.post(
        url,
        {
            entry.chosen: records[entry.valid_choice].pk,
            entry.fixed: records[entry.forged_fixed_key].pk,
            "stage": Stage.HIRED,
            "previous_stage": Stage.OFFER,
            "stage_changed_by": someone_else.pk,
            "stage_changed_at": "2000-01-01 00:00",
        },
    )
    assert response.status_code == 302
    assert response.url == entry.detail_url.format(pk=fixed.pk)
    assert Application.objects.count() == count + 1
    created = Application.objects.latest("pk")
    assert getattr(created, entry.fixed) == fixed
    assert getattr(created, entry.chosen) == records[entry.valid_choice]
    assert created.stage == Stage.APPLIED
    assert created.previous_stage is None
    assert created.stage_changed_by == employee
    assert started <= created.stage_changed_at <= timezone.now()
