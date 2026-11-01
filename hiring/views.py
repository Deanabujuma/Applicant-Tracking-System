from django.shortcuts import render


def workspace(request):
    """Placeholder hiring workspace. Phase 7 replaces this with the real workspace."""
    return render(request, "hiring/workspace.html")
