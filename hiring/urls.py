from django.urls import path

from . import views

app_name = "hiring"

urlpatterns = [
    path("", views.workspace, name="workspace"),
]
