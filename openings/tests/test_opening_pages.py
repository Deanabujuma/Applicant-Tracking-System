"""Phase 3 opening pages: create, list, IDs, status protection, skills, login."""

import pytest
from django.db import IntegrityError
from django.urls import reverse

from openings.models import JobOpening, OpeningStatus, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee_client(client, django_user_model):
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    return client


def opening_data(**overrides):
    data = {
        "title": "Data Analyst",
        "department": "Finance",
        "location": "",
        "description": "",
    }
    data.update(overrides)
    return data


# --- Create ----------------------------------------------------------------


def test_create_opening_with_only_title_and_department_starts_open(employee_client):
    response = employee_client.post(
        reverse("openings:create"), {"title": "Data Analyst", "department": "Finance"}
    )

    opening = JobOpening.objects.get()
    assert response.status_code == 302
    assert response.url == opening.get_absolute_url()
    assert opening.title == "Data Analyst"
    assert opening.department == "Finance"
    assert opening.status == OpeningStatus.OPEN
    assert opening.location == ""
    assert opening.description == ""
    assert opening.skills.count() == 0


@pytest.mark.parametrize("missing", ["title", "department"])
def test_title_and_department_are_required(employee_client, missing):
    response = employee_client.post(
        reverse("openings:create"), opening_data(**{missing: ""})
    )

    assert response.status_code == 200
    assert missing in response.context["form"].errors
    assert JobOpening.objects.count() == 0


def test_create_opening_with_skills(employee_client):
    python = Skill.objects.create(name="Python")
    sql = Skill.objects.create(name="SQL")

    employee_client.post(
        reverse("openings:create"), opening_data(skills=[python.pk, sql.pk])
    )

    assert set(JobOpening.objects.get().skills.all()) == {python, sql}


def test_same_skill_is_shared_across_openings(employee_client):
    python = Skill.objects.create(name="Python")

    employee_client.post(reverse("openings:create"), opening_data(skills=[python.pk]))
    employee_client.post(
        reverse("openings:create"),
        opening_data(title="Data Engineer", department="IT", skills=[python.pk]),
    )

    assert Skill.objects.count() == 1
    assert python.openings.count() == 2


# --- Same titles and unique IDs -------------------------------------------


def test_two_openings_can_have_the_same_title(employee_client):
    for department in ("Finance", "IT"):
        response = employee_client.post(
            reverse("openings:create"), opening_data(department=department)
        )
        assert response.status_code == 302

    assert JobOpening.objects.filter(title="Data Analyst").count() == 2
    page = employee_client.get(reverse("openings:list")).content.decode()
    assert "<td>Finance</td>" in page
    assert "<td>IT</td>" in page


def test_identical_openings_are_distinguished_by_unique_id(employee_client):
    first = JobOpening.objects.create(title="Data Analyst", department="Finance")
    second = JobOpening.objects.create(title="Data Analyst", department="Finance")
    assert first.pk != second.pk
    assert first.status == second.status

    listing = employee_client.get(reverse("openings:list")).content.decode()
    assert f"#{first.pk}" in listing
    assert f"#{second.pk}" in listing
    assert f'href="{first.get_absolute_url()}"' in listing
    assert f'href="{second.get_absolute_url()}"' in listing

    for opening in (first, second):
        detail = employee_client.get(opening.get_absolute_url()).content.decode()
        assert f"Opening #{opening.pk}" in detail


# --- List ordering ---------------------------------------------------------


def test_list_orders_by_title_department_then_pk(employee_client):
    eng_it = JobOpening.objects.create(title="Engineer", department="IT")
    analyst_it_older = JobOpening.objects.create(title="Analyst", department="IT")
    analyst_finance = JobOpening.objects.create(title="Analyst", department="Finance")
    analyst_it_newer = JobOpening.objects.create(title="Analyst", department="IT")

    response = employee_client.get(reverse("openings:list"))

    assert response.status_code == 200
    assert list(response.context["openings"]) == [
        analyst_finance,
        analyst_it_older,
        analyst_it_newer,
        eng_it,
    ]


def test_list_shows_id_title_department_status_and_skills(employee_client):
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")
    opening.skills.add(Skill.objects.create(name="Python"))

    page = employee_client.get(reverse("openings:list")).content.decode()

    for text in (f"#{opening.pk}", "Data Analyst", "Finance", "Open", "Python"):
        assert text in page


def test_header_has_openings_link(employee_client):
    page = employee_client.get(reverse("hiring:workspace")).content.decode()

    assert f'href="{reverse("openings:list")}"' in page


# --- Status can't be changed through the form ------------------------------


def test_status_is_not_a_form_field(employee_client):
    page = employee_client.get(reverse("openings:create")).content.decode()

    assert 'name="status"' not in page


def test_posted_status_is_ignored_on_create(employee_client):
    employee_client.post(
        reverse("openings:create"), opening_data(status=OpeningStatus.CLOSED)
    )

    assert JobOpening.objects.get().status == OpeningStatus.OPEN


def test_posted_status_is_ignored_on_edit(employee_client):
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")

    response = employee_client.post(
        reverse("openings:edit", kwargs={"pk": opening.pk}),
        opening_data(title="Senior Data Analyst", status=OpeningStatus.CLOSED),
    )

    assert response.status_code == 302
    opening.refresh_from_db()
    assert opening.title == "Senior Data Analyst"
    assert opening.status == OpeningStatus.OPEN


# --- Skill database constraint ---------------------------------------------


def test_database_rejects_skill_name_differing_only_by_capitalization():
    Skill.objects.create(name="Python")

    with pytest.raises(IntegrityError):
        Skill.objects.create(name="python")


# --- Login required --------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "needs_pk"),
    [("list", False), ("create", False), ("detail", True), ("edit", True)],
)
def test_every_opening_page_requires_login(client, name, needs_pk):
    kwargs = {}
    if needs_pk:
        kwargs["pk"] = JobOpening.objects.create(title="T", department="D").pk
    url = reverse(f"openings:{name}", kwargs=kwargs)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"


def test_inline_skill_endpoint_requires_login(client):
    url = reverse("openings:skill_create")

    response = client.post(url, {"new_skill_name": "Rust"}, HTTP_HX_REQUEST="true")

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"
    assert not Skill.objects.filter(name="Rust").exists()


def test_anonymous_post_cannot_create_or_edit_an_opening(client):
    opening = JobOpening.objects.create(title="Data Analyst", department="Finance")

    client.post(reverse("openings:create"), opening_data(title="Sneaky"))
    client.post(
        reverse("openings:edit", kwargs={"pk": opening.pk}),
        opening_data(title="Changed"),
    )

    assert JobOpening.objects.count() == 1
    opening.refresh_from_db()
    assert opening.title == "Data Analyst"
