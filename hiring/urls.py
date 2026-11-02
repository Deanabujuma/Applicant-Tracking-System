from django.urls import path

from . import views

app_name = "hiring"

urlpatterns = [
    path("", views.workspace, name="workspace"),
    path("applications/new/", views.application_create, name="application_create"),
    path("applications/<int:pk>/move/", views.move_application, name="move"),
]
