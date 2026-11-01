from django.contrib import admin

from .models import Skill


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """Administrator cleanup of shared skills (e.g. unused ones left by Cancel).

    Employees have no in-app way to delete skills. Deleting one here removes only
    its links to openings, never the openings.
    """

    list_display = ("name",)
    search_fields = ("name",)
