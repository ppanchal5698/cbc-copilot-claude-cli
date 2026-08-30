"""How a stored provider choice becomes the environment `claude` runs with.

This is the only place that translation happens. The worker, the settings
screen's test button and preflight all call `build_env`, because two
implementations of credential resolution would eventually disagree and the
disagreement would present as an authentication bug - the hardest kind to read.

The variables are not interchangeable, and getting them wrong fails as a 401
rather than as anything descriptive:

    ANTHROPIC_AUTH_TOKEN     -> Authorization: Bearer      (gateways)
    ANTHROPIC_API_KEY        -> x-api-key                  (Anthropic direct)
    CLAUDE_CODE_OAUTH_TOKEN  -> a claude.ai subscription token from `setup-token`
    CLAUDE_CODE_USE_BEDROCK  -> AWS credential chain, no Anthropic key at all
"""
from __future__ import annotations

import os
from typing import Any

from cbc_core import secrets

SUBSCRIPTION = "subscription"
ANTHROPIC_API = "anthropic_api"
BEDROCK = "bedrock"
GATEWAY = "gateway"
OLLAMA = "ollama"

MODES = (SUBSCRIPTION, ANTHROPIC_API, BEDROCK, GATEWAY, OLLAMA)

# Which stored field feeds which variable, and whether it holds a credential.
FIELDS: dict[str, dict[str, tuple[str, bool]]] = {
    SUBSCRIPTION: {
        "oauthToken": ("CLAUDE_CODE_OAUTH_TOKEN", True),
    },
    ANTHROPIC_API: {
        "apiKey": ("ANTHROPIC_API_KEY", True),
        "baseUrl": ("ANTHROPIC_BASE_URL", False),
        "model": ("ANTHROPIC_MODEL", False),
    },
    BEDROCK: {
        "awsRegion": ("AWS_REGION", False),
        "bedrockApiKey": ("AWS_BEARER_TOKEN_BEDROCK", True),
        "model": ("ANTHROPIC_MODEL", False),
        "smallFastModel": ("ANTHROPIC_DEFAULT_HAIKU_MODEL", False),
    },
    GATEWAY: {
        "baseUrl": ("ANTHROPIC_BASE_URL", False),
        "authToken": ("ANTHROPIC_AUTH_TOKEN", True),
        "model": ("ANTHROPIC_MODEL", False),
    },
    OLLAMA: {
        "baseUrl": ("ANTHROPIC_BASE_URL", False),
        "model": ("ANTHROPIC_MODEL", False),
        "smallFastModel": ("ANTHROPIC_DEFAULT_HAIKU_MODEL", False),
    },
}

# Every variable this module can set. Anything left over from the host
# environment is cleared, so switching provider actually switches provider
# instead of layering on top of a stale key.
MANAGED = {
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_USE_BEDROCK",
    "AWS_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
}

# Never handed to the Claude Code process itself.
#
# `MONGODB_URI` authenticates as root@admin, and pymongo is installed in the
# image, so a single Bash call could write to any collection - straight past the
# catalog server's read-only assertion, which governs its tools and not its
# credentials. The one thing in a run that legitimately needs a database is the
# catalog server, and it is given its own read-only string through the MCP
# config instead (see cbc_core/toolsets.py).
WITHHELD = {"MONGODB_URI", "MONGODB_READONLY_URI", "MONGODB_READONLY_PASSWORD"}

DEFAULT: dict[str, Any] = {"mode": SUBSCRIPTION}

# Where a provider base URL may point.
#
# `baseUrl` is exported as ANTHROPIC_BASE_URL and, in gateway mode, paired with a
# bearer token - so an arbitrary value means the credential is sent to an
# arbitrary host, and the settings screen's Test button confirms the redirection
# works. Anthropic, Bedrock and a gateway on this machine are allowed out of the
# box; anything else is a deliberate operator choice made through the
# environment, not something typed into a form.
DEFAULT_ALLOWED_HOSTS = (
    "api.anthropic.com",
    ".anthropic.com",
    ".amazonaws.com",
    "localhost",
    "127.0.0.1",
    "host.docker.internal",
    "litellm",
)


def allowed_hosts() -> tuple[str, ...]:
    extra = os.environ.get("ALLOWED_PROVIDER_HOSTS", "")
    return DEFAULT_ALLOWED_HOSTS + tuple(
        host.strip().lower() for host in extra.split(",") if host.strip()
    )


def check_base_url(value: str | None) -> None:
    """Raise ValueError when a base URL is not somewhere we may send a credential."""
    if not value:
        return
    from urllib.parse import urlsplit

    parsed = urlsplit(value if "//" in value else f"//{value}", scheme="https")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"base URL must be http or https, got {parsed.scheme!r}")

    host = (parsed.hostname or "").lower()
    permitted = allowed_hosts()
    if not any(host == entry or host.endswith(entry) for entry in permitted if entry):
        raise ValueError(
            f"{host!r} is not an allowed provider host. Add it to "
            "ALLOWED_PROVIDER_HOSTS if this is deliberate."
        )


def default_config() -> dict[str, Any]:
    return dict(DEFAULT)


def resolve_mode(config: dict[str, Any] | None) -> str:
    mode = (config or {}).get("mode") or SUBSCRIPTION
    return mode if mode in MODES else SUBSCRIPTION


def build_env(config: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    """Return (env for the subprocess, {field: source}).

    The environment wins over the database. On Fargate the credentials come from
    Secrets Manager, and a value typed into the settings screen must not be able
    to quietly replace them - so a variable already present is used as-is and
    reported as `env`, which is what the UI locks the field on.
    """
    config = config or default_config()
    mode = resolve_mode(config)

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in MANAGED and key not in WITHHELD
    }
    sources: dict[str, str] = {}

    for field, (variable, is_secret) in FIELDS[mode].items():
        from_env = os.environ.get(variable)
        if from_env:
            env[variable] = from_env
            sources[field] = "env"
            continue

        stored = config.get(field)
        value = secrets.decrypt(stored) if is_secret else stored
        if value:
            env[variable] = str(value)
            sources[field] = "db"

    if mode == BEDROCK:
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        # Bedrock resolves the region from the AWS profile when it is unset, but
        # a container has no profile, so an unset region silently lands on
        # us-east-1 where the model may not be enabled. Better to be explicit.
        env.setdefault("AWS_REGION", "us-east-1")

    if mode == OLLAMA:
        # Ollama speaks the Anthropic Messages API. The bearer value is ignored
        # by Ollama but must be non-empty so Claude Code routes away from a
        # subscription token in ~/.claude/.credentials.json.
        if "ANTHROPIC_AUTH_TOKEN" not in env:
            env["ANTHROPIC_AUTH_TOKEN"] = "ollama"
        # Explicitly empty - without this, a mounted subscription credential or
        # a stale ANTHROPIC_API_KEY in the shell wins over ANTHROPIC_BASE_URL.
        env["ANTHROPIC_API_KEY"] = ""
        if "ANTHROPIC_BASE_URL" not in env:
            env["ANTHROPIC_BASE_URL"] = os.environ.get(
                "OLLAMA_BASE_URL", "http://localhost:11434"
            )
        env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")

        # Phase agents declare `model: sonnet` in frontmatter. Without these,
        # Claude Code resolves those aliases to Anthropic IDs (claude-sonnet-5,
        # claude-haiku-4-5-20251001, …) and every Agent call fails against Ollama.
        main_model = env.get("ANTHROPIC_MODEL")
        if main_model:
            env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", main_model)
            env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", main_model)
            env.setdefault("CLAUDE_CODE_SUBAGENT_MODEL", main_model)
            env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", main_model)

    return env, sources


def secret_values(config: dict[str, Any] | None) -> list[str]:
    """Plaintext credentials in play, for redacting captured output."""
    config = config or default_config()
    mode = resolve_mode(config)
    found = []
    for field, (variable, is_secret) in FIELDS[mode].items():
        if not is_secret:
            continue
        value = os.environ.get(variable) or secrets.decrypt(config.get(field))
        if value:
            found.append(value)
    return found


def describe(config: dict[str, Any] | None) -> dict[str, Any]:
    """A one-line answer to 'what served this job?', safe to log and store."""
    config = config or default_config()
    mode = resolve_mode(config)
    env, sources = build_env(config)
    model = env.get("ANTHROPIC_MODEL") or "provider default"
    warnings: list[str] = []
    if mode == OLLAMA:
        warnings.append(
            "Ollama/local models may fail Agent-tool delegation; Anthropic Sonnet "
            "is recommended for pipeline jobs."
        )
        if model and ("cloud" in model.lower() or "gemma" in model.lower()):
            warnings.append(
                f"Model {model!r} may be unrecognized by Claude Code "
                "(watch for claude-code:unrecognized_model in job logs)."
            )
    return {
        "mode": mode,
        "model": model,
        "baseUrl": env.get("ANTHROPIC_BASE_URL"),
        "region": env.get("AWS_REGION") if mode == BEDROCK else None,
        "credentialSource": sources,
        "warnings": warnings,
    }


def public_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """The settings screen's view: every field, secrets masked, env fields locked."""
    config = config or default_config()
    mode = resolve_mode(config)
    _, sources = build_env(config)

    fields: dict[str, Any] = {}
    for field, (variable, is_secret) in FIELDS[mode].items():
        source = sources.get(field)
        if source == "env":
            value = secrets.mask(os.environ.get(variable)) if is_secret else os.environ.get(variable)
        else:
            value = secrets.mask(config.get(field)) if is_secret else config.get(field)
        fields[field] = {
            "value": value,
            "variable": variable,
            "secret": is_secret,
            "locked": source == "env",
            "configured": bool(value),
        }

    return {
        "mode": mode,
        "modes": list(MODES),
        "fields": fields,
        # Every mode's shape, not just the saved one. The settings screen has to
        # render the fields for a provider before it has been saved - otherwise
        # picking a new provider shows an empty form and there is no way in.
        "schema": {
            candidate: {
                field: {
                    "variable": variable,
                    "secret": is_secret,
                    "locked": bool(os.environ.get(variable)),
                    "configured": bool(
                        os.environ.get(variable)
                        or (config.get(field) if candidate == mode else None)
                    ),
                    "value": (
                        fields.get(field, {}).get("value") if candidate == mode else None
                    ),
                }
                for field, (variable, is_secret) in FIELDS[candidate].items()
            }
            for candidate in MODES
        },
        "updatedAt": config.get("updatedAt"),
        "updatedBy": config.get("updatedBy"),
    }
