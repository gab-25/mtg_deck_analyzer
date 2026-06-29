"""Tests for Zitadel authentication in the FastAPI web service."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient


@pytest.fixture
def session_data():
    """A dictionary representing mock session data."""
    return {}


@pytest.fixture
def client(tmp_path, monkeypatch, session_data):
    # Use an isolated SQLite database so tests need no Postgres.
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    # Clean any Zitadel env vars so standard tests behave normally
    monkeypatch.delenv("ZITADEL_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZITADEL_DOMAIN", raising=False)

    # Monkeypatch Request.session to return our local dict.
    # This intercepts all session interactions on the Request object.
    monkeypatch.setattr(Request, "session", property(lambda self: session_data))

    from mtg_deck_analyzer import app as app_module
    from mtg_deck_analyzer import db as db_module

    # Reset the lazy database engine
    db_module._engine = None
    db_module._SessionLocal = None

    with TestClient(app_module.app) as c:
        yield c


def test_index_shows_login_when_zitadel_enabled(client, monkeypatch):
    # Enable Zitadel authentication
    monkeypatch.setenv("ZITADEL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ZITADEL_DOMAIN", "https://auth.example.com")

    # Visit the index and verify it redirects/shows the login page
    r = client.get("/")
    assert r.status_code == 200
    assert "Login with Zitadel" in r.text
    assert "Authentication Required" in r.text


def test_create_deck_redirects_when_not_authenticated_and_zitadel_enabled(
    client, monkeypatch
):
    monkeypatch.setenv("ZITADEL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ZITADEL_DOMAIN", "https://auth.example.com")

    # Standard request
    r = client.post(
        "/decks", data={"name": "x", "decklist": "2 Forest"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"

    # HTMX request
    r = client.post(
        "/decks",
        data={"name": "x", "decklist": "2 Forest"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == "/auth/login"


def test_login_redirects_to_zitadel(client, monkeypatch):
    monkeypatch.setenv("ZITADEL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ZITADEL_DOMAIN", "https://auth.example.com")

    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "https://auth.example.com/oauth/v2/authorize" in loc
    assert "client_id=test-client-id" in loc
    assert "scope=openid+profile+email" in loc
    assert "state=" in loc


def test_logout_clears_session(client, monkeypatch, session_data):
    monkeypatch.setenv("ZITADEL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ZITADEL_DOMAIN", "https://auth.example.com")

    # 1. Login by populating mock session data
    session_data["user"] = {
        "name": "Jace Beleren",
        "email": "jace@ravnica.gov",
        "preferred_username": "jace",
    }

    # 2. Home page should be accessible when authenticated
    r = client.get("/")
    assert r.status_code == 200
    assert "Analyze a deck" in r.text
    assert "Jace Beleren" in r.text

    # 3. Logout
    r = client.get("/auth/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    # 4. Now session data should be empty (or at least user is removed)
    assert "user" not in session_data

    # 5. Visiting index should show the login page
    r = client.get("/")
    assert r.status_code == 200
    assert "Login with Zitadel" in r.text
    assert "Authentication Required" in r.text
