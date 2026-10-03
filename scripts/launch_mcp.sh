#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "================================================="
echo " Antigravity MCP Cluster Runner & Cognitive Router"
echo "================================================="

OPTION="${1:-3}"

case "$OPTION" in
    1|guard)
        echo "▶ Launching OPTION 1: Local Antigravity Guard MCP Server (standalone)..."
        exec uv run python mcp_guard_server.py
        ;;
    2|inspector)
        echo "▶ Launching OPTION 2: MCP Inspector UI..."
        exec npx @modelcontextprotocol/inspector uv run python mcp_guard_server.py
        ;;
    3|gateway)
        echo "▶ Launching OPTION 3: Antigravity Gateway (Cognitive Router) with MCP Routing..."
        echo "  Config: .antigravity/mcp_config.json"
        echo "  Endpoints available:"
        echo "    GET  http://127.0.0.1:8080/mcp/servers"
        echo "    GET  http://127.0.0.1:8080/mcp/tools"
        echo "    POST http://127.0.0.1:8080/mcp/call"
        echo "    POST http://127.0.0.1:8080/mcp/rpc/{server_name}"
        exec uv run python gateway.py --mcp-config .antigravity/mcp_config.json
        ;;
    *)
        echo "Usage: $0 [1|2|3|guard|inspector|gateway]"
        echo "  1 | guard     - Standalone Antigravity Guard FastMCP Server"
        echo "  2 | inspector - MCP Inspector Web Debugger"
        echo "  3 | gateway   - Full Antigravity Cognitive Router Gateway (Default)"
        exit 1
        ;;
esac
