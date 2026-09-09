# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "snowflake-connector-python",
#     "python-dotenv",
# ]
# ///
import json
import sys
import os
import re
import subprocess
_snowflake_conn = None
from dotenv import load_dotenv
from snowflake.connector import connect

load_dotenv()


def run_sql_query(query):
    global _snowflake_conn

    try:
        if _snowflake_conn is None or _snowflake_conn.is_closed():
            _snowflake_conn = connect(
                account=os.environ["SNOWFLAKE_ACCOUNT"],
                user=os.environ["SNOWFLAKE_USER"],
                password=os.environ["SNOWFLAKE_PASSWORD"],
                warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
                database=os.environ.get("SNOWFLAKE_DATABASE", "CUSTOM_AGENT"),
                schema=os.environ.get("SNOWFLAKE_SCHEMA", "STAGING")
            )

        cursor = _snowflake_conn.cursor()

        try:
            cursor.execute(query)
            return cursor.fetchall()
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

def validate_model(sql: str, model_type: str) -> str:
    """Performs deterministic template/rule checks for Data Vault model SQL."""
    violations = []
    lower_sql = sql.lower()

    if model_type == "staging":
        required_ctes = ["with src as", "logic as", "rename as", "filter as", "join_layer as", "final as"]
        for cte in required_ctes:
            if cte not in lower_sql:
                violations.append(f"Missing required staging CTE: {cte}")

        if "source('control', 'ref_source_system')" not in lower_sql and "source(\"control\", \"ref_source_system\")" not in lower_sql:
            violations.append("Staging must join REF_SOURCE_SYSTEM via source('control', 'REF_SOURCE_SYSTEM').")

        if re.search(r"'[^']*'\s+as\s+rec_src", lower_sql):
            violations.append("REC_SRC must not be hardcoded as a string literal in staging.")
        if re.search(r"'[^']*'\s+as\s+bkcc", lower_sql):
            violations.append("BKCC must not be hardcoded as a string literal in staging.")

        if "md5_binary" not in lower_sql:
            violations.append("Staging must compute hash columns using MD5_BINARY.")

    elif model_type in ["hub", "link"]:
        if "ghost_records as" not in lower_sql:
            violations.append("Hub/Link must include ghost_records CTE.")

        for sentinel in ["md5_binary(upper('0'))", "md5_binary(upper('-1'))", "md5_binary(upper('-2'))"]:
            if sentinel not in lower_sql:
                violations.append(f"Missing ghost hash sentinel: {sentinel}")

        md5_positions = [m.start() for m in re.finditer(r"md5_binary", lower_sql)]
        if md5_positions:
            ghost_idx = lower_sql.find("ghost_records as")
            if ghost_idx == -1:
                violations.append("MD5_BINARY found but ghost_records CTE is missing.")
            else:
                for pos in md5_positions:
                    if pos < ghost_idx:
                        violations.append("Hub/Link must not recompute business hashes outside ghost_records.")
                        break

        if "row_number() over" not in lower_sql:
            violations.append("Hub/Link must include QUALIFY ROW_NUMBER() dedup pattern.")

    elif model_type == "satellite":
        if "md5_binary" in lower_sql:
            violations.append("Satellite must not compute MD5_BINARY; HASHDIFF must come from staging.")
        if "hashdiff" not in lower_sql:
            violations.append("Satellite must select HASHDIFF from staging.")
        if "bkcc" in lower_sql:
            violations.append("Satellite must exclude BKCC.")
        if "row_number() over" not in lower_sql:
            violations.append("Satellite must dedup with QUALIFY ROW_NUMBER().")
        if "partition by" not in lower_sql or "hashdiff" not in lower_sql:
            violations.append("Satellite dedup must partition by parent _HK and HASHDIFF.")

    else:
        violations.append(f"Unsupported model_type: {model_type}")

    result = {
        "pass": len(violations) == 0,
        "violations": violations
    }
    return json.dumps(result)

def handle_input():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")

            # 1. INITIALIZE HANDLER
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "cortex-mcp-server", "version": "1.0.0"}
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            # 2. LIST TOOLS HANDLER
            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "sql_exec_tool",
                                "description": "Execute read-only or DDL SQL queries against your Snowflake database.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "The exact SQL string to execute."}
                                    },
                                    "required": ["query"]
                                }
                            },
                            {
                                "name": "validate_model_tool",
                                "description": "Deterministically check generated Data Vault dbt model SQL against DV_STANDARD.md rules (hashing location, ghost records, dedup pattern, source/ref usage). Returns pass/fail and a list of violations.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "sql": {"type": "string", "description": "The full SQL text of the model to validate."},
                                        "model_type": {
                                            "type": "string",
                                            "enum": ["staging", "hub", "link", "satellite"],
                                            "description": "Which layer this model belongs to."
                                        }
                                    },
                                    "required": ["sql", "model_type"]
                                }
                            }
                        ]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            # 3. CALL TOOL HANDLER
            if method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name == "sql_exec_tool":
                    query = arguments.get("query", "SELECT 1;")
                    output_text = run_sql_query(query)
                elif tool_name == "validate_model_tool":
                    output_text = validate_model(
                        sql=arguments.get("sql", ""),
                        model_type=arguments.get("model_type", "")
                    )
                else:
                    output_text = f"Error: Unknown tool name '{tool_name}'"

                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": output_text}]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0", 
                "id": req.get("id", 0) if 'req' in locals() else 0, 
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    handle_input()