import pytest
from django.db import IntegrityError

from candidates.models import Candidate, Source


@pytest.mark.django_db
def test_database_rejects_email_differing_only_by_capitalization():
    """Case-insensitive unique email is enforced by the database, not only by forms."""
    Candidate.objects.create(
        first_name="Ana",
        last_name="Lopez",
        email="Ana.Lopez@Example.com",
        source=Source.JOB_BOARD,
    )

    with pytest.raises(IntegrityError):
        Candidate.objects.create(
            first_name="Ana",
            last_name="Lopez",
            email="ana.lopez@example.com",
            source=Source.REFERRAL,
        )
