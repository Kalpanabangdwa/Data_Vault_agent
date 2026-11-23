"""
Shared plumbing for every MCP server in this folder.

Each server file only declares its TOOLS (name, description, input schema)
and a HANDLERS dict mapping tool name -> Python function. This module runs
the stdio JSON-RPC loop that VS Code talks to:

    initialize  -> server info
    tools/list  -> the TOOLS list
    tools/call  -> HANDLERS[name](**arguments), returned as text

Not an MCP server itself; it is imported by the *_mcp.py files.
"""

import json
import os
import sys

# Project root = the folder that contains mcp_servers/ (and .env, .github/, dv_gen_project/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

PROTOCOL_VERSION = "2024-11-05"


def _send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def serve(server_name, tools, handlers, version="1.0.0"):
    """Run the MCP stdio loop until stdin closes."""

    for line in sys.stdin:
        if not line.strip():
            continue

        req = {}
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")

            if method == "initialize":
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": server_name, "version": version},
                    },
                })

            elif method == "tools/list":
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": tools},
                })

            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {}) or {}

                if name not in handlers:
                    raise ValueError(f"Unknown tool name '{name}'")

                text = handlers[name](**arguments)

                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}]},
                })

            # Notifications (e.g. notifications/initialized) need no reply.

        except Exception as e:
            _send({
                "jsonrpc": "2.0",
                "id": req.get("id", 0) if isinstance(req, dict) else 0,
                "error": {"code": -32603, "message": str(e)},
            })
