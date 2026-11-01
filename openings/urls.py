from django.urls import path

from . import views

app_name = "openings"

urlpatterns = [
    path("", views.JobOpeningListView.as_view(), name="list"),
    path("new/", views.JobOpeningCreateView.as_view(), name="create"),
    path("<int:pk>/", views.JobOpeningDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.JobOpeningUpdateView.as_view(), name="edit"),
    path("<int:pk>/close/", views.close_opening, name="close"),
    path("<int:pk>/reopen/", views.reopen_opening, name="reopen"),
    path("<int:pk>/delete/", views.delete_opening, name="delete"),
    path("skills/new/", views.add_skill_inline, name="skill_create"),
    path("skills/remove/", views.remove_skill_inline, name="skill_remove"),
]
