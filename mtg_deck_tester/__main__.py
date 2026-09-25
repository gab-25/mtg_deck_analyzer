"""Run the web service locally: ``python -m mtg_deck_tester``.

Applies any pending database migrations, then starts Django's HTTP server. The
bind address/port come from ``HOST``/``PORT`` and auto-reload from ``RELOAD``.
"""

import os


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtg_deck_tester.settings")

    from django.core.management import execute_from_command_line

    host = os.environ.get("HOST", "0.0.0.0")
    port = os.environ.get("PORT", "8000")
    reload = os.environ.get("RELOAD", "").lower() in {"1", "true", "yes"}

    execute_from_command_line(["manage.py", "migrate", "--noinput"])

    argv = ["manage.py", "runserver", f"{host}:{port}"]
    if not reload:
        argv.append("--noreload")
    execute_from_command_line(argv)


if __name__ == "__main__":
    main()
