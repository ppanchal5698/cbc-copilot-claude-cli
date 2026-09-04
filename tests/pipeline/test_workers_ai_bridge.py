"""Workers AI Anthropic bridge: translation and mocked upstream calls."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from cbc.workers_ai_bridge.app import create_app
from cbc.workers_ai_bridge.translate import (
    anthropic_to_openai_messages,
    anthropic_to_run_messages,
    needs_openai_path,
    openai_to_anthropic_response,
    run_to_anthropic_response,
)


def test_run_messages_flatten_system_and_text_blocks():
    body = {
        "system": "You are helpful.",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
            },
        ],
    }
    assert anthropic_to_run_messages(body) == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]


def test_needs_openai_path_when_tools_or_tool_use_present():
    assert needs_openai_path({"tools": [{"name": "Bash"}]}) is True
    assert (
        needs_openai_path(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Bash",
                                "input": {"command": "ls"},
                            }
                        ],
                    }
                ]
            }
        )
        is True
    )
    assert needs_openai_path({"messages": [{"role": "user", "content": "hi"}]}) is False


def test_openai_round_trip_maps_tool_calls():
    messages, tools = anthropic_to_openai_messages(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_abc",
                            "name": "Bash",
                            "input": {"command": "pwd"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_abc",
                            "content": "/app",
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "name": "Bash",
                    "description": "run a shell command",
                    "input_schema": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                    },
                }
            ],
        }
    )
    assert messages[0]["role"] == "assistant"
    assert messages[0]["tool_calls"][0]["function"]["name"] == "Bash"
    assert messages[1] == {
        "role": "tool",
        "tool_call_id": "toolu_abc",
        "content": "/app",
    }
    assert tools[0]["function"]["name"] == "Bash"

    anthropic = openai_to_anthropic_response(
        {
            "id": "chatcmpl-1",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "Bash",
                                    "arguments": '{"command":"ls"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        model="@cf/test",
    )
    assert anthropic["stop_reason"] == "tool_use"
    assert anthropic["content"][0]["type"] == "tool_use"
    assert anthropic["content"][0]["input"] == {"command": "ls"}
    assert anthropic["usage"]["input_tokens"] == 10


def test_run_response_maps_result_response_string():
    anthropic = run_to_anthropic_response(
        {"success": True, "result": {"response": "Once upon a time"}},
        model="@cf/moonshotai/kimi-k2.7-code",
    )
    assert anthropic["role"] == "assistant"
    assert anthropic["content"][0]["text"] == "Once upon a time"
    assert anthropic["model"] == "@cf/moonshotai/kimi-k2.7-code"


def test_messages_endpoint_forwards_to_ai_run(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc123")
    monkeypatch.setenv("CLOUDFLARE_AIG_TOKEN", "cfut-test")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"success": True, "result": {"response": "story text"}},
        )

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("cbc.workers_ai_bridge.app.httpx.AsyncClient", PatchedAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/v1/messages",
        headers={"x-api-key": "anything", "anthropic-version": "2023-06-01"},
        json={
            "model": "@cf/moonshotai/kimi-k2.7-code",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "Write a story"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"][0]["text"] == "story text"
    assert captured["url"].endswith("/ai/run/@cf/moonshotai/kimi-k2.7-code")
    assert captured["auth"] == "Bearer cfut-test"
    assert captured["body"]["messages"][0]["content"] == "Write a story"


def test_messages_endpoint_rejects_missing_credentials(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AIG_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_WORKERAI_API_TOKEN", raising=False)
    # Avoid leaking a developer .env into the bridge under test.
    monkeypatch.setattr(
        "cbc.workers_ai_bridge.app.envfile.read",
        lambda: {},
    )
    client = TestClient(create_app())
    response = client.post(
        "/v1/messages",
        headers={"x-api-key": "x"},
        json={
            "model": "@cf/test",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 503


def test_upstream_error_is_passed_through(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc123")
    monkeypatch.setenv("CLOUDFLARE_AIG_TOKEN", "tok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"message": "bad token"}]})

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("cbc.workers_ai_bridge.app.httpx.AsyncClient", PatchedAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/v1/messages",
        headers={"x-api-key": "x"},
        json={
            "model": "@cf/test",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 401
    assert "bad token" in json.dumps(response.json())
