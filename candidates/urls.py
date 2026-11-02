from django.urls import path

from . import views

app_name = "candidates"

urlpatterns = [
    path("", views.CandidateListView.as_view(), name="list"),
    path("new/", views.CandidateCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CandidateDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CandidateUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.delete_candidate, name="delete"),
    path("<int:pk>/archive/", views.archive_candidate, name="archive"),
    path("<int:pk>/unarchive/", views.unarchive_candidate, name="unarchive"),
]
