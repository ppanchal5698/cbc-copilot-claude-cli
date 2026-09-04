"""FastAPI Anthropic-compatible front door for Cloudflare Workers AI."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cbc.core import envfile
from cbc.workers_ai_bridge.translate import (
    anthropic_stream_events,
    anthropic_to_openai_messages,
    anthropic_to_run_messages,
    needs_openai_path,
    openai_to_anthropic_response,
    run_to_anthropic_response,
)

log = logging.getLogger("cbc.workers_ai_bridge")

DEFAULT_PORT = 8787


def _env(name: str) -> str:
    """Process env first, then the repo `.env` Settings writes."""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    return (envfile.read().get(name) or "").strip()


def _account_id() -> str:
    return _env("CLOUDFLARE_ACCOUNT_ID")


def _api_token() -> str:
    return _env("CLOUDFLARE_AIG_TOKEN") or _env("CLOUDFLARE_WORKERAI_API_TOKEN")


def _api_root(account: str) -> str:
    override = _env("CLOUDFLARE_BASE_API_URL")
    if override:
        return override if override.endswith("/") else f"{override}/"
    return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/"


def _chat_completions_url(account: str) -> str:
    return (
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    )


def create_app() -> FastAPI:
    app = FastAPI(title="CBC Workers AI bridge", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request) -> dict[str, int]:
        body = await request.json()
        # Claude Code sometimes probes this; rough char/4 estimate is enough.
        total = 0
        system = body.get("system")
        if system:
            total += len(system if isinstance(system, str) else json.dumps(system))
        for message in body.get("messages") or []:
            content = message.get("content")
            total += len(content if isinstance(content, str) else json.dumps(content))
        return {"input_tokens": max(1, total // 4)}

    @app.post("/v1/messages")
    async def messages(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="x-api-key"),
        authorization: str | None = Header(default=None),
    ) -> Any:
        if not x_api_key and not (
            authorization and authorization.lower().startswith("bearer ")
        ):
            raise HTTPException(status_code=401, detail="missing x-api-key")

        account = _account_id()
        token = _api_token()
        if not account or not token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AIG_TOKEN "
                    "(or CLOUDFLARE_WORKERAI_API_TOKEN) are required"
                ),
            )

        body = await request.json()
        model = (body.get("model") or _env("ANTHROPIC_MODEL") or "").strip()
        if not model:
            raise HTTPException(status_code=400, detail="model is required")

        stream = bool(body.get("stream"))
        try:
            anthropic = await _forward(account, token, model, body)
        except httpx.HTTPStatusError as exc:
            detail: Any
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            log.warning(
                "Workers AI upstream %s: %s",
                exc.response.status_code,
                detail,
            )
            return JSONResponse(status_code=exc.response.status_code, content=detail)
        except httpx.HTTPError as exc:
            log.exception("Workers AI request failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if not stream:
            return JSONResponse(anthropic)

        async def event_stream():
            for event in anthropic_stream_events(anthropic):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


async def _forward(
    account: str,
    token: str,
    model: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(120.0, connect=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        if needs_openai_path(body):
            try:
                return await _via_chat_completions(
                    client, headers, account, model, body
                )
            except httpx.HTTPStatusError as exc:
                # Some free models reject tools; fall back to plain /ai/run.
                if exc.response.status_code in (400, 422) and body.get("tools"):
                    log.info(
                        "chat/completions rejected tools (%s); falling back to /ai/run",
                        exc.response.status_code,
                    )
                    return await _via_run(client, headers, account, model, body)
                raise
        return await _via_run(client, headers, account, model, body)


async def _via_run(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    account: str,
    model: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    url = f"{_api_root(account)}{model}"
    payload = {"messages": anthropic_to_run_messages(body)}
    max_tokens = body.get("max_tokens")
    if max_tokens:
        payload["max_tokens"] = max_tokens
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("success") is False:
        errors = data.get("errors") or data
        raise HTTPException(status_code=502, detail=errors)
    return run_to_anthropic_response(data, model=model)


async def _via_chat_completions(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    account: str,
    model: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    messages, tools = anthropic_to_openai_messages(body)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    max_tokens = body.get("max_tokens")
    if max_tokens:
        payload["max_tokens"] = max_tokens
    response = await client.post(
        _chat_completions_url(account), headers=headers, json=payload
    )
    response.raise_for_status()
    return openai_to_anthropic_response(response.json(), model=model)


app = create_app()
