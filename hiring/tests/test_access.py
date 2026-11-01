from django.conf import settings
from django.shortcuts import resolve_url
from django.urls import reverse


def test_anonymous_visitor_is_redirected_to_login(client):
    """An anonymous request to the workspace never sees content; it is sent to login."""
    workspace_url = reverse("hiring:workspace")

    response = client.get(workspace_url)

    assert response.status_code == 302
    assert response.url == f"{resolve_url(settings.LOGIN_URL)}?next={workspace_url}"


def test_active_employee_can_log_in_reach_workspace_and_log_out(
    client, django_user_model
):
    """An admin-created, active employee logs in, sees the workspace, and can log out."""
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    # Access model: hiring employees are ordinary active users, not Django admin staff.
    assert employee.is_active is True
    assert employee.is_staff is False
    assert employee.is_superuser is False
    login_url = reverse("login")
    workspace_url = reverse("hiring:workspace")

    login_page = client.get(login_url)
    assert login_page.status_code == 200
    assert 'name="username"' in login_page.content.decode()
    assert 'name="password"' in login_page.content.decode()

    response = client.post(
        login_url, {"username": "jsmith", "password": "correct-horse-42"}
    )
    assert response.status_code == 302
    assert response.url == workspace_url

    workspace = client.get(workspace_url)
    assert workspace.status_code == 200
    page = workspace.content.decode()
    assert "jsmith" in page
    assert f'action="{reverse("logout")}"' in page

    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert response.url == login_url

    after_logout = client.get(workspace_url)
    assert after_logout.status_code == 302
    assert after_logout.url == f"{login_url}?next={workspace_url}"


def test_deactivated_employee_cannot_log_in_or_reach_workspace(
    client, django_user_model
):
    """An employee whose account an admin deactivated cannot log in or see the workspace."""
    django_user_model.objects.create_user(
        username="former", password="correct-horse-42", is_active=False
    )
    login_url = reverse("login")
    workspace_url = reverse("hiring:workspace")

    response = client.post(
        login_url, {"username": "former", "password": "correct-horse-42"}
    )

    assert response.status_code == 200  # login page re-rendered, no redirect
    assert response.context["form"].non_field_errors()
    assert "_auth_user_id" not in client.session

    workspace = client.get(workspace_url)
    assert workspace.status_code == 302
    assert workspace.url == f"{login_url}?next={workspace_url}"


def test_deactivating_logged_in_employee_ends_their_access(client, django_user_model):
    """Deactivating an account revokes access even for a session that is already logged in."""
    employee = django_user_model.objects.create_user(
        username="jsmith", password="correct-horse-42"
    )
    client.force_login(employee)
    workspace_url = reverse("hiring:workspace")
    assert client.get(workspace_url).status_code == 200

    employee.is_active = False
    employee.save()

    workspace = client.get(workspace_url)
    assert workspace.status_code == 302
    assert workspace.url == f"{reverse('login')}?next={workspace_url}"
