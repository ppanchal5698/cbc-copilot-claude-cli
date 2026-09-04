"""Run the Workers AI Anthropic bridge: python -m cbc.workers_ai_bridge."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("WORKERS_AI_BRIDGE_HOST", "0.0.0.0")
    port = int(os.environ.get("WORKERS_AI_BRIDGE_PORT", "8787"))
    uvicorn.run(
        "cbc.workers_ai_bridge.app:app",
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
