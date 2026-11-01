import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    "path",
    ["/signup/", "/register/", "/accounts/signup/", "/accounts/register/"],
)
def test_no_public_registration_routes(client, path):
    """Accounts are admin-created only, so no sign-up URL exists."""
    assert client.get(path).status_code == 404


def test_login_page_offers_no_signup_link(client):
    page = client.get(reverse("login")).content.decode().lower()

    assert "sign up" not in page
    assert "signup" not in page
    assert "register" not in page


def test_base_template_loads_tailwind_and_htmx(client):
    """Every page extends the base layout, which loads the built CSS and HTMX."""
    page = client.get(reverse("login")).content.decode()

    assert 'href="/static/css/tailwind.css"' in page
    assert 'src="/static/js/htmx.min.js"' in page
