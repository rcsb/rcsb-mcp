#!/usr/bin/env bash
# Run the MCP over the HTTP transport locally so report LINKS resolve in development.
#
# rcsb_render_report returns a self-contained link (GET /r?d=...) only when
# RCSB_MCP_REPORT_BASE_URL is set. The link is served by the SAME app that serves
# /mcp, so it only resolves when the server runs over HTTP (stdio serves no routes).
# This script starts that HTTP server with the base URL pointed at itself, so a
# link the tool emits opens locally with no extra setup.
#
#   Endpoints:  POST http://localhost:$PORT/mcp   (connect your MCP client here)
#               GET  http://localhost:$PORT/r?d=  (the report render page)
#               GET  http://localhost:$PORT/healthz
#
# Usage:  scripts/dev-server.sh          # port 8080
#         PORT=9000 scripts/dev-server.sh
set -euo pipefail

PORT="${PORT:-8080}"
export RCSB_MCP_REPORT_BASE_URL="${RCSB_MCP_REPORT_BASE_URL:-http://localhost:${PORT}}"
# One process here, so the in-memory store honestly resolves its own short links.
# Opt it in as "shared" so you exercise the real /r/<id> -> 302 -> /r?d= flow locally
# without running Redis. NEVER set this on a multi-replica deployment.
export RCSB_MCP_REPORT_SHARED_STORE="${RCSB_MCP_REPORT_SHARED_STORE:-true}"

echo "rcsb-mcp (HTTP)  ->  ${RCSB_MCP_REPORT_BASE_URL}"
echo "  MCP:    ${RCSB_MCP_REPORT_BASE_URL}/mcp"
echo "  report: ${RCSB_MCP_REPORT_BASE_URL}/r?d=..."
exec uvicorn rcsb_mcp.server:create_app --factory --host 127.0.0.1 --port "${PORT}"
