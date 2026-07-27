# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create an unprivileged user up front (uid/gid 1000 to match the Helm
# podSecurityContext: runAsUser / runAsGroup / fsGroup = 1000).
RUN groupadd --gid 1000 appuser \
    && useradd --create-home --uid 1000 --gid 1000 appuser

# Install the package and its dependencies. Copy build metadata + source only
# (keeps the layer cache friendly and the image lean). The [redis] extra ships the
# client for the shared short-link store, so setting RCSB_MCP_REDIS_URL actually
# enables short report links across replicas (without it, `import redis` fails and
# the tool falls back to self-contained links).
COPY pyproject.toml README.md ./
COPY src ./src
# './' not '.': hadolint's DL3013 (pin pip versions) only exempts args it recognizes
# as local paths, and '.[redis]' doesn't match its './' prefix check. Same install.
RUN pip install './[redis]'

USER appuser

EXPOSE 8080

# Liveness: confirm the server is accepting connections on the port.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',8080)); s.close()" || exit 1

# Serve the MCP over the streamable-HTTP transport (endpoint: POST /mcp).
# create_app is the FastMCP streamable-HTTP ASGI app factory (--factory builds it on start).
CMD ["uvicorn", "rcsb_mcp.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
