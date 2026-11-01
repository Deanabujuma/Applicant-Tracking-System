# Applicant-Tracking-System
CIDM 3312 Project #1 - Applicant Tracking System

## Running the project

Requires [uv](https://docs.astral.sh/uv/). Node.js is **not** needed: django-tailwind-cli downloads a standalone Tailwind CLI binary with DaisyUI built in.

```sh
uv sync                                   # install locked dependencies
uv run python manage.py migrate           # create the SQLite database
uv run python manage.py tailwind build    # build static/css/tailwind.css (not committed)
uv run python manage.py createsuperuser   # administrator account
uv run python manage.py runserver
```

`static/css/tailwind.css` is generated and ignored by Git. Run `tailwind build` after cloning and after changing templates. During development, `uv run python manage.py tailwind runserver` runs the dev server and rebuilds CSS on change.

## Accounts

There is no public sign-up. An administrator creates each hiring employee's account in Django admin (`/admin/`) as an active, non-staff user. Deactivating the account (unchecking **Active**) revokes access.

## Checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
```
