from django.urls import path

from . import views

app_name = "hiring"

urlpatterns = [
    path("", views.workspace, name="workspace"),
    path("applications/new/", views.application_create, name="application_create"),
]
