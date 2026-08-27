"""Provider resolution, credential handling, and what must never leak.

The provider layer is where a wrong answer is expensive in two directions: get
the variable wrong and every job fails with an unexplained 401, get the handling
wrong and a credential ends up in a database, a log, or the audit trail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TEST_DB = "cbc_opshub_test_provider"

from api.services import provider, secrets  # noqa: E402
from api.tests.conftest import opshub_client  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with opshub_client(TEST_DB) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No test may inherit a real credential from the developer's shell."""
    for variable in provider.MANAGED:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("APP_SECRET_KEY", "test-key-for-provider-tests")


# ── the variables themselves ────────────────────────────────────────────────


def test_each_mode_sets_the_variable_that_provider_actually_reads():
    """These are not interchangeable: the wrong one arrives in a header nobody reads."""
    env, _ = provider.build_env({"mode": provider.ANTHROPIC_API, "apiKey": "sk-ant-plain"})
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-plain"  # x-api-key
    assert "ANTHROPIC_AUTH_TOKEN" not in env

    env, _ = provider.build_env(
        {"mode": provider.GATEWAY, "baseUrl": "http://litellm:4000", "authToken": "sk-gw"}
    )
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-gw"  # Authorization: Bearer
    assert env["ANTHROPIC_BASE_URL"] == "http://litellm:4000"
    assert "ANTHROPIC_API_KEY" not in env

    env, _ = provider.build_env({"mode": provider.SUBSCRIPTION, "oauthToken": "sk-ant-oat-x"})
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat-x"


def test_bedrock_sets_its_flag_and_never_leaves_the_region_to_chance():
    """A container has no AWS profile, so an unset region lands somewhere arbitrary."""
    env, _ = provider.build_env({"mode": provider.BEDROCK})
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert env["AWS_REGION"] == "us-east-1"

    env, _ = provider.build_env({"mode": provider.BEDROCK, "awsRegion": "eu-west-1"})
    assert env["AWS_REGION"] == "eu-west-1"


def test_switching_provider_clears_the_previous_one(monkeypatch):
    """A stale key left in the environment would silently outrank the new choice."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # present but empty
    env, _ = provider.build_env({"mode": provider.BEDROCK, "awsRegion": "us-east-2"})

    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_unmanaged_environment_is_passed_through(monkeypatch):
    """The subprocess still needs PATH, HOME and MONGODB_URI to work at all."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://example/db")
    env, _ = provider.build_env({"mode": provider.SUBSCRIPTION})
    assert env["MONGODB_URI"] == "mongodb://example/db"
    assert "PATH" in env


# ── precedence ──────────────────────────────────────────────────────────────


def test_environment_beats_the_database_and_says_so(monkeypatch):
    """On Fargate the credential comes from Secrets Manager.

    A value typed into the settings screen must not quietly replace it, and the
    screen has to be able to show the estimator why their edit will not apply.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-environment")

    config = {"mode": provider.ANTHROPIC_API, "apiKey": secrets.encrypt("sk-ant-from-database")}
    env, sources = provider.build_env(config)

    assert env["ANTHROPIC_API_KEY"] == "sk-ant-from-environment"
    assert sources["apiKey"] == "env"
    assert provider.public_config(config)["fields"]["apiKey"]["locked"] is True


def test_the_database_is_used_when_the_environment_is_silent():
    config = {"mode": provider.ANTHROPIC_API, "apiKey": secrets.encrypt("sk-ant-stored")}
    env, sources = provider.build_env(config)

    assert env["ANTHROPIC_API_KEY"] == "sk-ant-stored"
    assert sources["apiKey"] == "db"
    assert provider.public_config(config)["fields"]["apiKey"]["locked"] is False


# ── secrets ─────────────────────────────────────────────────────────────────


def test_a_credential_round_trips_but_is_not_stored_in_the_clear():
    stored = secrets.encrypt("sk-ant-api03-secret-value")
    assert stored.startswith("enc:")
    assert "sk-ant-api03-secret-value" not in stored
    assert secrets.decrypt(stored) == "sk-ant-api03-secret-value"


def test_a_credential_encrypted_under_a_lost_key_reads_as_unconfigured(monkeypatch):
    """Changing APP_SECRET_KEY must not stop the settings screen from loading."""
    stored = secrets.encrypt("sk-ant-old-key")
    monkeypatch.setenv("APP_SECRET_KEY", "a-completely-different-key")

    assert secrets.decrypt(stored) is None
    assert secrets.mask(stored) is None


def test_masking_shows_enough_to_recognise_and_not_enough_to_use():
    masked = secrets.mask(secrets.encrypt("sk-ant-api03-abcdefghijklmnop"))
    assert masked.startswith("sk-a") and masked.endswith("mnop")
    assert "api03-abcdefghij" not in masked


@pytest.mark.parametrize(
    "leaked",
    [
        "sk-ant-api03-abcdefghijklmnopqrstuv",
        "sk-or-v1-abcdefghijklmnopqrstuvwxyz",
        "nvapi-abcdefghijklmnopqrstuvwxyz",
        "AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_recognisable_credentials_are_stripped_from_captured_output(leaked):
    """worker/main.py stores 8000 characters of this on every job."""
    cleaned = secrets.redact(f"error: request failed with key {leaked} at line 3")
    assert leaked not in cleaned
    assert "[redacted]" in cleaned


def test_an_unrecognisable_gateway_token_is_stripped_because_it_was_passed_in():
    """A bearer token can be any string, so pattern matching alone is not enough."""
    token = "totally-arbitrary-gateway-credential"
    cleaned = secrets.redact(f"401 rejected {token}", [token])
    assert token not in cleaned


def test_redaction_leaves_a_short_value_alone():
    """Redacting 'abc' would blank out ordinary prose across the whole log."""
    assert secrets.redact("failed at step abc", ["abc"]) == "failed at step abc"


# ── the endpoints ───────────────────────────────────────────────────────────


def test_settings_start_from_a_working_default(client):
    body = client.get("/api/settings/claude").json()
    assert body["mode"] == provider.SUBSCRIPTION
    assert set(body["modes"]) == set(provider.MODES)


def test_saving_a_credential_returns_it_masked_and_never_in_the_clear(client):
    response = client.put(
        "/api/settings/claude",
        json={"mode": "gateway", "baseUrl": "http://litellm:4000", "authToken": "sk-gw-secret"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["mode"] == "gateway"
    assert "sk-gw-secret" not in response.text
    assert body["fields"]["authToken"]["configured"] is True
    assert body["fields"]["baseUrl"]["value"] == "http://litellm:4000"


def test_a_masked_value_sent_back_unedited_keeps_the_stored_credential(client):
    """The screen renders the mask; saving an unrelated field must not destroy the key.

    This asserted only that *something* was still configured, which the mask
    itself satisfied - so it passed while Save was quietly overwriting the real
    credential with `sk-a********p-me`. It now checks the actual stored value.
    """
    secret = "sk-ant-api03-keep-me-intact-abcdef"
    client.put(
        "/api/settings/claude",
        json={"mode": "anthropic_api", "apiKey": secret, "model": "sonnet"},
    )
    masked = client.get("/api/settings/claude").json()["fields"]["apiKey"]["value"]

    client.put(
        "/api/settings/claude",
        json={"mode": "anthropic_api", "apiKey": masked, "model": "opus"},
    )

    after = client.get("/api/settings/claude").json()
    assert after["fields"]["model"]["value"] == "opus"

    # The credential itself, not merely "configured" - which a mask satisfies too.
    from pymongo import MongoClient

    from api.config import settings as app_settings

    raw = MongoClient(app_settings.mongodb_uri)
    try:
        stored = raw[TEST_DB]["settings"].find_one({"_id": "claude"})
    finally:
        raw.close()

    assert secrets.decrypt(stored["apiKey"]) == secret
    assert "****" not in secrets.decrypt(stored["apiKey"])


def test_saving_settings_records_the_change_without_the_values(client):
    """The trail has to show that a credential changed, and never what it became."""
    from pymongo import MongoClient

    from api.config import settings as app_settings

    client.put(
        "/api/settings/claude",
        json={"mode": "anthropic_api", "apiKey": "sk-ant-must-not-be-audited"},
    )

    raw = MongoClient(app_settings.mongodb_uri)
    try:
        entries = list(
            raw[TEST_DB]["auditLog"].find({"action": "settings.claude.update"})
        )
    finally:
        raw.close()

    assert entries, "the change itself must be recorded"
    assert "apiKey" in entries[-1]["after"]["changed"]
    assert "sk-ant-must-not-be-audited" not in str(entries)
