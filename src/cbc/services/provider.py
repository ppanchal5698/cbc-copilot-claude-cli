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
    ANTHROPIC_CUSTOM_HEADERS -> extra headers (Cloudflare: cf-aig-authorization)
"""
from __future__ import annotations

import os
from typing import Any

from cbc.core import envfile, secrets

SUBSCRIPTION = "subscription"
ANTHROPIC_API = "anthropic_api"
BEDROCK = "bedrock"
CLOUDFLARE = "cloudflare"
GATEWAY = "gateway"
OLLAMA = "ollama"

MODES = (SUBSCRIPTION, ANTHROPIC_API, BEDROCK, CLOUDFLARE, GATEWAY, OLLAMA)

CF_ANTHROPIC = "anthropic"
CF_BEDROCK = "bedrock"
CF_VERTEX = "vertex"
CF_WORKERS = "workers"
CF_ROUTES = (CF_ANTHROPIC, CF_BEDROCK, CF_VERTEX, CF_WORKERS)

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
    CLOUDFLARE: {
        "accountId": ("CLOUDFLARE_ACCOUNT_ID", False),
        "gatewayId": ("CLOUDFLARE_GATEWAY_ID", False),
        "gatewayToken": ("CLOUDFLARE_AIG_TOKEN", True),
        "cfRoute": ("CLOUDFLARE_ROUTE", False),
        "apiKey": ("ANTHROPIC_API_KEY", True),
        "awsRegion": ("AWS_REGION", False),
        "vertexProject": ("ANTHROPIC_VERTEX_PROJECT_ID", False),
        "vertexRegion": ("CLOUD_ML_REGION", False),
        "baseUrl": ("ANTHROPIC_BASE_URL", False),
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
    "ANTHROPIC_BEDROCK_REGION_PREFIX",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLOUD_ML_REGION",
    "CLAUDE_CODE_SKIP_VERTEX_AUTH",
    "ANTHROPIC_CUSTOM_HEADERS",
    "AWS_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_GATEWAY_ID",
    "CLOUDFLARE_AIG_TOKEN",
    "CLOUDFLARE_ROUTE",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
}

# Claude Code aliases. A value that is one of these is left as-is; a concrete
# Bedrock ID is what we pin the family variables to.
_MODEL_ALIASES = frozenset({"sonnet", "opus", "haiku"})

# India has Claude only through Global CRIS, not the apac. geo profiles that
# Claude Code would otherwise derive from an ap-* AWS_REGION.
_INDIA_REGIONS = frozenset({"ap-south-1", "ap-south-2"})

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
    "gateway.ai.cloudflare.com",
    ".cloudflare.com",
    ".workers.dev",
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


def _bedrock_region_prefix(region: str) -> str:
    """The CRIS prefix Claude Code should try first for this AWS region.

    Matches Claude Code's own table, with India (`ap-south-1` / `ap-south-2`)
    forced to `global` — those regions do not host `apac.` profiles.
    """
    name = (region or "").strip().lower()
    if name in _INDIA_REGIONS:
        return "global"
    if name.startswith("us-gov-"):
        return "us-gov"
    if name.startswith("us-"):
        return "us"
    if name.startswith("eu-"):
        return "eu"
    if name.startswith("ap-"):
        return "apac"
    return "global"


def _as_inference_profile(model_id: str, prefix: str) -> str:
    """Rewrite a bare foundation-model ID; leave aliases, profiles and ARNs alone."""
    value = model_id.strip()
    if value.startswith("anthropic."):
        return f"{prefix}.{value}"
    return value


def _is_model_alias(model_id: str) -> bool:
    return model_id.strip().lower() in _MODEL_ALIASES


def resolve_cf_route(
    config: dict[str, Any] | None,
    env: dict[str, str] | None = None,
) -> str:
    """AI Gateway route. Unknown values fall back to Anthropic, not Workers."""
    raw = ""
    if env and env.get("CLOUDFLARE_ROUTE"):
        raw = env["CLOUDFLARE_ROUTE"]
    elif config:
        raw = str(config.get("cfRoute") or "")
    raw = raw.strip().lower() or CF_ANTHROPIC
    return raw if raw in CF_ROUTES else CF_ANTHROPIC


def _gateway_root(account: str, gateway: str) -> str:
    return f"https://gateway.ai.cloudflare.com/v1/{account.strip()}/{gateway.strip()}"


def _uses_ai_gateway(url: str | None) -> bool:
    return bool(url) and "gateway.ai.cloudflare.com" in url.lower()


def _pin_model_aliases(env: dict[str, str], *, pin_haiku: bool = False) -> None:
    """Map Claude Code's sonnet/opus/haiku aliases onto the configured model.

    Phase agents declare `model: sonnet` or `model: haiku`. Without the sonnet
    and opus pins Claude Code resolves those aliases to Anthropic catalog IDs
    the provider cannot serve. Haiku is left unset on Bedrock/Cloudflare so a
    distinct `ANTHROPIC_DEFAULT_HAIKU_MODEL` (Settings smallFastModel) can win;
    Ollama still pins Haiku because it has no Anthropic Haiku catalog.
    """
    main_model = env.get("ANTHROPIC_MODEL")
    if not main_model:
        return
    env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", main_model)
    env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", main_model)
    env.setdefault("CLAUDE_CODE_SUBAGENT_MODEL", main_model)
    if pin_haiku:
        env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", main_model)


def _apply_cloudflare(env: dict[str, str], config: dict[str, Any]) -> None:
    """Translate stored Cloudflare pieces into the Claude Code variables.

    Claude Code does not speak Workers AI. The documented path is AI Gateway,
    which exposes Anthropic, Bedrock, and Vertex as Anthropic-compatible
    endpoints. A fourth route accepts a typed URL that already speaks
    `/v1/messages` (a Workers bridge you deployed elsewhere).
    """
    route = resolve_cf_route(config, env)
    env["CLOUDFLARE_ROUTE"] = route
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    gateway = env.get("CLOUDFLARE_GATEWAY_ID", "").strip()
    token = env.get("CLOUDFLARE_AIG_TOKEN", "").strip()
    root = _gateway_root(account, gateway) if account and gateway else ""
    workers_url = env.get("ANTHROPIC_BASE_URL", "").strip()

    attach_gateway_header = bool(token) and (
        route != CF_WORKERS or _uses_ai_gateway(workers_url)
    )
    if attach_gateway_header:
        env.setdefault("ANTHROPIC_CUSTOM_HEADERS", f"cf-aig-authorization: Bearer {token}")

    if route == CF_ANTHROPIC:
        if root:
            env["ANTHROPIC_BASE_URL"] = f"{root}/anthropic"
        if "ANTHROPIC_API_KEY" not in env and token:
            env["ANTHROPIC_API_KEY"] = token
        return

    if route == CF_BEDROCK:
        region = (env.get("AWS_REGION") or "us-east-1").strip()
        env["AWS_REGION"] = region
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        env["CLAUDE_CODE_SKIP_BEDROCK_AUTH"] = "1"
        if root:
            env["ANTHROPIC_BEDROCK_BASE_URL"] = (
                f"{root}/aws-bedrock/bedrock-runtime/{region}/"
            )
        env.pop("ANTHROPIC_BASE_URL", None)
        return

    if route == CF_VERTEX:
        env["CLAUDE_CODE_USE_VERTEX"] = "1"
        env["CLAUDE_CODE_SKIP_VERTEX_AUTH"] = "1"
        if root:
            env["ANTHROPIC_VERTEX_BASE_URL"] = f"{root}/google-vertex-ai/v1"
        env.pop("ANTHROPIC_BASE_URL", None)
        return

    # workers — typed Anthropic-compatible bridge. OSS @cf/ models do not
    # reliably call the Agent tool, so aliases pin onto the one configured ID.
    if token and "ANTHROPIC_API_KEY" not in env:
        env["ANTHROPIC_API_KEY"] = token
    _pin_model_aliases(env)


def endpoint_urls(config: dict[str, Any] | None) -> list[str]:
    """Base URLs this provider will send a credential to. Used by Settings save."""
    env, _ = build_env(config)
    found: list[str] = []
    for key in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_BEDROCK_BASE_URL",
        "ANTHROPIC_VERTEX_BASE_URL",
    ):
        value = env.get(key)
        if value:
            found.append(value)
    return found


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
    file_env = envfile.read()

    for field, (variable, is_secret) in FIELDS[mode].items():
        from_env = os.environ.get(variable)
        if from_env:
            env[variable] = from_env
            sources[field] = "env"
            continue

        from_file = file_env.get(variable)
        if from_file:
            env[variable] = from_file
            sources[field] = "dotenv"
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
        # Env wins, same as every other managed variable. An operator who has
        # already pinned a prefix in Secrets Manager must not have it replaced.
        prefix = (
            os.environ.get("ANTHROPIC_BEDROCK_REGION_PREFIX")
            or file_env.get("ANTHROPIC_BEDROCK_REGION_PREFIX")
            or _bedrock_region_prefix(env["AWS_REGION"])
        )
        env["ANTHROPIC_BEDROCK_REGION_PREFIX"] = prefix
        for variable in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"):
            current = env.get(variable)
            if current:
                env[variable] = _as_inference_profile(current, prefix)
        # Phase agents declare `model: sonnet`. Without these pins Claude Code
        # resolves `opus` to Opus 5 from its Bedrock catalog and falls back with
        # "Opus 5 not available". A concrete ID is what we have; an alias is
        # left to the catalog, steered only by the region prefix above.
        main_model = env.get("ANTHROPIC_MODEL")
        if main_model and not _is_model_alias(main_model):
            _pin_model_aliases(env)

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

        # Phase agents declare `model: sonnet` / `model: haiku` in frontmatter.
        # Without these pins Claude Code resolves those aliases to Anthropic IDs
        # and every Agent call fails against Ollama. Haiku must pin here: there
        # is no Anthropic Haiku catalog on this provider.
        if env.get("ANTHROPIC_MODEL"):
            _pin_model_aliases(env, pin_haiku=True)

    if mode == CLOUDFLARE:
        _apply_cloudflare(env, config)

    return env, sources


def secret_values(config: dict[str, Any] | None) -> list[str]:
    """Plaintext credentials in play, for redacting captured output."""
    config = config or default_config()
    mode = resolve_mode(config)
    found = []
    file_env = envfile.read()
    for field, (variable, is_secret) in FIELDS[mode].items():
        if not is_secret:
            continue
        value = (
            os.environ.get(variable)
            or file_env.get(variable)
            or secrets.decrypt(config.get(field))
        )
        if value:
            found.append(value)
    return found


# Variables Settings is allowed to write into `.env`. Derived pins
# (DEFAULT_SONNET / OPUS / SUBAGENT) stay spawn-time only.
_PERSISTED = frozenset(
    {
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_USE_BEDROCK",
        "AWS_REGION",
        "AWS_BEARER_TOKEN_BEDROCK",
        "ANTHROPIC_CUSTOM_HEADERS",
        "ANTHROPIC_BEDROCK_BASE_URL",
        "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
        "CLAUDE_CODE_USE_VERTEX",
        "ANTHROPIC_VERTEX_BASE_URL",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "CLOUD_ML_REGION",
        "CLAUDE_CODE_SKIP_VERTEX_AUTH",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_GATEWAY_ID",
        "CLOUDFLARE_AIG_TOKEN",
        "CLOUDFLARE_ROUTE",
    }
)


def persist_env_file(config: dict[str, Any]) -> bool:
    """Mirror the saved provider onto `.env`. Secrets are stored in plaintext there.

    The file is gitignored and chmod 600. Process env still wins, so a Fargate
    task role is not replaced by whatever was typed last. Returns False when
    the file cannot be written; Mongo still holds the live copy.

    Cloudflare writes the *constructed* Claude variables (gateway URL, custom
    header, skip-auth flags), not only the raw Mongo pieces.
    """
    mode = resolve_mode(config)
    updates: dict[str, str | None] = {key: None for key in _PERSISTED}
    for field, (variable, is_secret) in FIELDS[mode].items():
        if variable not in _PERSISTED:
            continue
        stored = config.get(field)
        value = secrets.decrypt(stored) if is_secret else stored
        if value:
            updates[variable] = str(value)
    if mode == BEDROCK:
        updates["CLAUDE_CODE_USE_BEDROCK"] = "1"
    if mode == CLOUDFLARE:
        constructed = {key: value for key, value in updates.items() if value}
        _apply_cloudflare(constructed, config)
        for key in _PERSISTED:
            updates[key] = constructed.get(key)
    return envfile.upsert(updates)


def supports_subagents(config: dict[str, Any] | None) -> bool:
    """Whether this provider can be asked to delegate with the Agent tool.

    The pipeline prompts hand each phase to a registered subagent. A model that
    cannot make that call does not fail loudly - it reads the instruction, has no
    way to follow it, and spends its turns circling. An observed Ollama run made
    seven tool calls in twelve minutes, delegated nothing, and wrote no output.

    So the capability decides the prompt: where delegation is unavailable the run
    is told to do the phase work itself, with the same tools and the same outputs.
    """
    cfg = config or default_config()
    mode = resolve_mode(cfg)
    if mode == OLLAMA:
        return False
    if mode == CLOUDFLARE and resolve_cf_route(cfg) == CF_WORKERS:
        return False
    return True


def describe(config: dict[str, Any] | None) -> dict[str, Any]:
    """A one-line answer to 'what served this job?', safe to log and store."""
    config = config or default_config()
    mode = resolve_mode(config)
    env, sources = build_env(config)
    model = env.get("ANTHROPIC_MODEL") or "provider default"
    warnings: list[str] = []
    if mode == BEDROCK:
        typed = (
            os.environ.get("ANTHROPIC_MODEL")
            or envfile.read().get("ANTHROPIC_MODEL")
            or config.get("model")
        )
        if typed and str(typed) != model:
            warnings.append(
                f"Foundation model ID {typed!r} was rewritten to inference profile "
                f"{model!r} for {env.get('AWS_REGION')}."
            )
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
    cf_route = resolve_cf_route(config, env) if mode == CLOUDFLARE else None
    if mode == CLOUDFLARE and cf_route == CF_WORKERS:
        warnings.append(
            "Workers AI / OSS @cf/ models may fail Agent-tool delegation; "
            "Anthropic via AI Gateway is recommended for pipeline jobs."
        )
    region = None
    if mode == BEDROCK or cf_route == CF_BEDROCK:
        region = env.get("AWS_REGION")
    elif cf_route == CF_VERTEX:
        region = env.get("CLOUD_ML_REGION")
    return {
        "mode": mode,
        "model": model,
        "supportsSubagents": supports_subagents(config),
        "baseUrl": (
            env.get("ANTHROPIC_BASE_URL")
            or env.get("ANTHROPIC_BEDROCK_BASE_URL")
            or env.get("ANTHROPIC_VERTEX_BASE_URL")
        ),
        "region": region,
        "credentialSource": sources,
        "warnings": warnings,
    }


def public_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """The settings screen's view: every field, secrets masked, env fields locked."""
    config = config or default_config()
    mode = resolve_mode(config)
    _, sources = build_env(config)
    file_env = envfile.read()

    fields: dict[str, Any] = {}
    for field, (variable, is_secret) in FIELDS[mode].items():
        source = sources.get(field)
        if source == "env":
            raw = os.environ.get(variable)
        elif source == "dotenv":
            raw = file_env.get(variable)
        else:
            stored = config.get(field)
            raw = secrets.decrypt(stored) if is_secret else stored
        value = secrets.mask(raw) if is_secret else raw
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
                        or file_env.get(variable)
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
