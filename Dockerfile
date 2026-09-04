# API and worker share one image.
#
# They need the same things: Python for the MCP servers, the hooks and the
# business logic, and the Claude Code CLI itself. The API needs the CLI too - it
# is what drives the OAuth sign-in flow on the settings page - so building two
# nearly identical images would only let them drift.

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_MAJOR=22

# System packages, in one layer:
#   - curl/ca-certificates/gnupg: fetching the NodeSource key
#   - git: Claude Code shells out to it
#   - poppler-utils: Claude Code's Read tool renders PDF pages via pdftoppm
#   - libpango/libcairo/libgdk-pixbuf: WeasyPrint's native dependencies, so the
#     proposal PDF renders here even though it cannot on a bare Windows host
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git poppler-utils \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8 \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Claude Code refuses --dangerously-skip-permissions when running as root, so an
# unattended job would fail at spawn. Every process here runs as `cbc`.
RUN useradd --create-home --uid 1000 --shell /bin/bash cbc

WORKDIR /app

# Dependencies before source, so editing a router does not reinstall the world.
COPY requirements.txt ./
COPY mcp-servers/pyproject.toml ./mcp-servers/
RUN pip install -r requirements.txt

COPY --chown=cbc:cbc . /app
RUN pip install -e ./mcp-servers

# The mounted data directories must exist and be writable before the volumes are
# attached, or the first upload fails on a root-owned mount point.
#
# The chmod is not redundant with the file's mode in git. Windows checkouts run
# with core.fileMode=false, so the execute bit is not tracked from there and the
# script was committed 100644 - which Docker Desktop tolerates and a Linux host
# does not, failing at container start with "permission denied" on the
# entrypoint. Setting it here means the image is correct whatever the checkout
# did.
RUN mkdir -p /app/projects /app/pricebooks /app/.cache /app/.index /home/cbc/.claude \
    && chown -R cbc:cbc /app /home/cbc \
    && chmod +x /app/docker/entrypoint.sh

USER cbc
ENV HOME=/home/cbc \
    PATH="/home/cbc/.local/bin:${PATH}"

EXPOSE 8001

# The entrypoint declares /app trusted; see docker/entrypoint.sh for why that
# cannot be done at build time.
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Overridden per service in docker-compose.yml. The API is the sensible default.
# The domain package lives under src/, so both applications can import `cbc`.
ENV PYTHONPATH="/app:/app/src"

CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
