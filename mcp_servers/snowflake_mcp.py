# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "snowflake-connector-python",
#     "python-dotenv",
# ]
# ///

"""
Snowflake MCP server  (registered as "snowflake-mcp" in .vscode/mcp.json)

Tool:
  sql_exec_tool   run one SQL statement against Snowflake and return rows as JSON

Used by: dv-model-generator (schema discovery via INFORMATION_SCHEMA.COLUMNS
and the REC_SRC/BKCC lookup in CONTROL.REF_SOURCE_SYSTEM).

Credentials come from .env in the project root:
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD   (required)
  SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA (optional)

The connection is opened lazily on the first query and reused afterwards.
"""

import json
import os

from dotenv import load_dotenv
from snowflake.connector import connect

from mcp_base import ENV_FILE, serve

load_dotenv(ENV_FILE, override=True)

_snowflake_conn = None


def run_sql_query(query):
    """Execute SQL against Snowflake and return the result as JSON text."""

    global _snowflake_conn

    if not query:
        raise ValueError("query is required.")

    try:
        if _snowflake_conn is None or _snowflake_conn.is_closed():
            _snowflake_conn = connect(
                account=os.environ["SNOWFLAKE_ACCOUNT"],
                user=os.environ["SNOWFLAKE_USER"],
                password=os.environ["SNOWFLAKE_PASSWORD"],
                warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
                database=os.environ.get("SNOWFLAKE_DATABASE", "CUSTOM_AGENT"),
                schema=os.environ.get("SNOWFLAKE_SCHEMA", "STAGING"),
            )

        cursor = _snowflake_conn.cursor()

        try:
            cursor.execute(query)

            # SELECT / SHOW / DESCRIBE style queries
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                return json.dumps(
                    [dict(zip(columns, row)) for row in rows],
                    default=str,
                    indent=2,
                )

            # DDL / commands that don't return rows
            return json.dumps({"success": True, "rowcount": cursor.rowcount})

        finally:
            cursor.close()

    except Exception:
        if _snowflake_conn is not None:
            try:
                _snowflake_conn.close()
            except Exception:
                pass
        _snowflake_conn = None
        raise


TOOLS = [
    {
        "name": "sql_exec_tool",
        "description": "Execute SQL queries against the configured Snowflake database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Exact SQL string to execute.",
                }
            },
            "required": ["query"],
        },
    },
]

HANDLERS = {
    "sql_exec_tool": run_sql_query,
}


if __name__ == "__main__":
    serve("snowflake-mcp", TOOLS, HANDLERS)
