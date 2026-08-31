"""Who may do what.

Before this, the Next.js proxy's only check was "is anyone signed in", and it
then forwarded every path with the service token. Any estimator could read which
provider credentials were configured, repoint the gateway at a host of their
choosing, start CLI processes, or delete a price book.
"""
from __future__ import annotations

import pytest
from pymongo import MongoClient

from api.config import settings
from tests.shared import TEST_ACTOR, opshub_client

TEST_DB = "cbc_opshub_test_authz"


@pytest.fixture(scope="module")
def client():
    # One client, one event loop: the motor client is a module global, so two
    # live TestClients in one file would bind it to whichever loop started last.
    with opshub_client(TEST_DB, role="admin") as test_client:
        yield test_client


@pytest.fixture()
def as_role():
    """Change the signed-in user's role for one test."""
    raw = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)

    def set_role(role: str) -> None:
        raw[TEST_DB]["users"].update_one({"email": TEST_ACTOR}, {"$set": {"role": role}})

    try:
        yield set_role
    finally:
        set_role("admin")
        raw.close()


SETTINGS_ROUTES = [
    ("get", "/api/settings/claude", None),
    ("put", "/api/settings/claude", {"mode": "subscription"}),
    ("post", "/api/settings/claude/test", {"mode": "subscription"}),
]


@pytest.mark.parametrize("method, path, body", SETTINGS_ROUTES)
def test_an_estimator_cannot_reach_provider_settings(
    client, as_role, method, path, body
) -> None:
    as_role("estimator")
    call = getattr(client, method)
    response = call(path) if body is None else call(path, json=body)

    assert response.status_code == 403, f"{method.upper()} {path} was not refused"
    assert "not permitted" in response.json()["detail"]


def test_admin_can_read_provider_settings(client, as_role) -> None:
    as_role("admin")
    assert client.get("/api/settings/claude").status_code == 200


def test_an_unknown_actor_is_refused(client) -> None:
    """No user row means no role, which must not default to permitted."""
    response = client.get(
        "/api/settings/claude", headers={"X-Actor": "nobody@example.com"}
    )
    assert response.status_code == 403


def test_an_estimator_cannot_delete_a_price_book(client, as_role) -> None:
    book = client.post(
        "/api/price-books", json={"vendor": "Hager", "program": "Buying"}
    ).json()

    as_role("estimator")
    assert client.delete(f"/api/price-books/{book['id']}").status_code == 403

    as_role("admin")
    assert client.delete(f"/api/price-books/{book['id']}").status_code == 204


def test_an_estimator_still_does_their_own_job(client, as_role) -> None:
    """Authorization must not lock the ordinary user out of estimating."""
    as_role("estimator")

    created = client.post("/api/projects", json={"name": "Ordinary work", "state": "OH"})
    assert created.status_code == 201
    code = created.json()["code"]

    assert client.get(f"/api/projects/{code}/quote").status_code == 200
    assert (
        client.post(
            f"/api/projects/{code}/quote/lines",
            json={"part": "150CX18", "description": "Hinge", "cost": 10.0},
        ).status_code
        == 201
    )
    assert client.get("/api/catalog/products").status_code == 200
    assert client.get("/api/price-books").status_code == 200


# ── a base URL is where a bearer token gets sent ───────────────────────────


def test_a_base_url_off_the_allowlist_is_refused(client, as_role) -> None:
    as_role("admin")
    response = client.put(
        "/api/settings/claude",
        json={
            "mode": "gateway",
            "baseUrl": "https://evil.example.com",
            "authToken": "sk-or-abcdefghijklmnopqrstuvwxyz",
        },
    )
    assert response.status_code == 400
    assert "not an allowed provider host" in response.json()["detail"]


@pytest.mark.parametrize(
    "url",
    ["https://api.anthropic.com", "http://localhost:4000", "http://host.docker.internal:4000"],
)
def test_the_documented_providers_are_allowed(url: str) -> None:
    from api.services import provider

    provider.check_base_url(url)  # must not raise


def test_a_non_http_scheme_is_refused() -> None:
    from api.services import provider

    with pytest.raises(ValueError, match="http or https"):
        provider.check_base_url("file:///etc/passwd")


def test_an_operator_can_widen_the_allowlist(monkeypatch) -> None:
    from api.services import provider

    with pytest.raises(ValueError):
        provider.check_base_url("https://gateway.internal.corp")

    monkeypatch.setenv("ALLOWED_PROVIDER_HOSTS", "gateway.internal.corp")
    provider.check_base_url("https://gateway.internal.corp")


# ── the sign-in endpoint is the one thing reachable unauthenticated ────────


def test_repeated_sign_in_attempts_are_throttled(client) -> None:
    from api.routers import auth

    auth._attempts.clear()
    body = {"email": "someone@example.com", "password": "wrong"}

    codes = [client.post("/api/auth/verify", json=body).status_code for _ in range(12)]

    assert codes[0] == 401, "a single wrong password is just wrong"
    assert 429 in codes, "unlimited guesses against an unauthenticated endpoint"
    auth._attempts.clear()
