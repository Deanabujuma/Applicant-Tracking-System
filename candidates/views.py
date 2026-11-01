from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CandidateForm
from .models import Candidate


class CandidateListView(ListView):
    model = Candidate  # ordered by Candidate.Meta.ordering: last name, first name, pk


class CandidateCreateView(CreateView):
    model = Candidate
    form_class = CandidateForm


class CandidateDetailView(DetailView):
    model = Candidate


class CandidateUpdateView(UpdateView):
    model = Candidate
    form_class = CandidateForm
