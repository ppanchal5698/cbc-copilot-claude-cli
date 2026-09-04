"""Pure request/response translation between Anthropic Messages and Workers AI."""

from __future__ import annotations

import json
import uuid
from typing import Any


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        if block.get("type") == "text":
            return str(block.get("text") or "")
        if block.get("type") == "tool_result":
            content = block.get("content")
            if isinstance(content, list):
                return "".join(_block_text(part) for part in content)
            return str(content or "")
    return ""


def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_block_text(block) for block in content)
    return str(content)


def _has_tool_payload(body: dict[str, Any]) -> bool:
    if body.get("tools"):
        return True
    for message in body.get("messages") or []:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") in (
                "tool_use",
                "tool_result",
            ):
                return True
    return False


def needs_openai_path(body: dict[str, Any]) -> bool:
    """Tool-bearing Anthropic requests need chat/completions, not plain /ai/run."""
    return _has_tool_payload(body)


def anthropic_to_run_messages(body: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten an Anthropic Messages body into Workers AI `{messages}` for /ai/run."""
    out: list[dict[str, str]] = []
    system = body.get("system")
    if system:
        out.append({"role": "system", "content": _flatten_content(system)})
    for message in body.get("messages") or []:
        role = message.get("role") or "user"
        if role not in ("user", "assistant", "system"):
            role = "user"
        text = _flatten_content(message.get("content"))
        if text:
            out.append({"role": role, "content": text})
    if not out:
        out.append({"role": "user", "content": ""})
    return out


def anthropic_to_openai_messages(
    body: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Convert Anthropic messages/tools to OpenAI chat.completions shape."""
    messages: list[dict[str, Any]] = []
    system = body.get("system")
    if system:
        messages.append({"role": "system", "content": _flatten_content(system)})

    for message in body.get("messages") or []:
        role = message.get("role") or "user"
        content = message.get("content")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            messages.append({"role": role, "content": _flatten_content(content)})
            continue

        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        tool_results: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            kind = block.get("type")
            if kind == "text":
                text_parts.append(str(block.get("text") or ""))
            elif kind == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": block.get("name") or "tool",
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    }
                )
            elif kind == "tool_result":
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id") or "",
                        "content": _flatten_content(block.get("content")),
                    }
                )

        if role == "assistant" and tool_calls:
            assistant: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            joined = "".join(text_parts).strip()
            if joined:
                assistant["content"] = joined
            messages.append(assistant)
        elif tool_results and role == "user":
            # Anthropic packs tool_result blocks into a user turn; OpenAI wants
            # one tool message per result.
            preamble = "".join(text_parts).strip()
            if preamble:
                messages.append({"role": "user", "content": preamble})
            messages.extend(tool_results)
        else:
            messages.append({"role": role, "content": "".join(text_parts)})

    tools_out: list[dict[str, Any]] | None = None
    raw_tools = body.get("tools") or []
    if raw_tools:
        tools_out = []
        for tool in raw_tools:
            if not isinstance(tool, dict):
                continue
            tools_out.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name") or "tool",
                        "description": tool.get("description") or "",
                        "parameters": tool.get("input_schema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
    return messages, tools_out


def _usage_from_any(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        usage = {**usage, **result["usage"]}
    return {
        "input_tokens": int(
            usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or usage.get("prompt_token_count")
            or 0
        ),
        "output_tokens": int(
            usage.get("output_tokens")
            or usage.get("completion_tokens")
            or usage.get("completion_token_count")
            or 0
        ),
    }


def _assistant_text_from_run(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if isinstance(result.get("response"), str):
            return result["response"]
        message = result.get("message")
        if isinstance(message, dict):
            return _flatten_content(message.get("content"))
        if isinstance(result.get("content"), str):
            return result["content"]
    if isinstance(payload.get("response"), str):
        return payload["response"]
    # Some models return the text at the top level under `result` as a list.
    if isinstance(result, list):
        return "".join(_flatten_content(item) for item in result)
    return ""


def run_to_anthropic_response(
    payload: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    """Map a Workers AI `/ai/run` JSON body to an Anthropic Messages response."""
    text = _assistant_text_from_run(payload)
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": _usage_from_any(payload),
    }


def openai_to_anthropic_response(
    payload: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    """Map an OpenAI chat.completions body to Anthropic Messages."""
    choices = payload.get("choices") or []
    message: dict[str, Any] = {}
    finish = "stop"
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        finish = choices[0].get("finish_reason") or "stop"

    content: list[dict[str, Any]] = []
    text = message.get("content")
    if isinstance(text, str) and text:
        content.append({"type": "text", "text": text})

    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            parsed = {"raw": raw_args}
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": fn.get("name") or "tool",
                "input": parsed if isinstance(parsed, dict) else {"value": parsed},
            }
        )

    if not content:
        content.append({"type": "text", "text": ""})

    stop_reason = "tool_use" if any(b.get("type") == "tool_use" for b in content) else "end_turn"
    if finish == "length":
        stop_reason = "max_tokens"

    return {
        "id": payload.get("id") or f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": _usage_from_any(payload),
    }


def anthropic_stream_events(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Emit a minimal Anthropic SSE event sequence for a completed message."""
    message_start = {
        "type": "message_start",
        "message": {
            "id": response["id"],
            "type": "message",
            "role": "assistant",
            "model": response.get("model"),
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": 0,
            },
        },
    }
    events: list[dict[str, Any]] = [message_start]
    for index, block in enumerate(response.get("content") or []):
        events.append(
            {
                "type": "content_block_start",
                "index": index,
                "content_block": (
                    {"type": "text", "text": ""}
                    if block.get("type") == "text"
                    else {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": {},
                    }
                ),
            }
        )
        if block.get("type") == "text":
            events.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": block.get("text") or ""},
                }
            )
        else:
            events.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block.get("input") or {}),
                    },
                }
            )
        events.append({"type": "content_block_stop", "index": index})
    events.append(
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": response.get("stop_reason") or "end_turn",
                "stop_sequence": None,
            },
            "usage": {
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            },
        }
    )
    events.append({"type": "message_stop"})
    return events
