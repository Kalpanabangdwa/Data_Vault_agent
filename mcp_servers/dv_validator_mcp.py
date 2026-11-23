# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""
Data Vault validator MCP server  (registered as "dv-validator-mcp")

Tool:
  validate_model_tool   deterministic, rule-based checks of generated Data Vault
                        SQL. No LLM, no database. Returns {"pass": bool, "violations": [...]}

Used by: dv-model-generator, before any SQL is shown to a human.

To adapt the pipeline to another domain, replace validate_model() with your
own rule set; the rest of the pipeline does not change.
"""

import json
import re

from mcp_base import serve


def validate_model(sql: str = "", model_type: str = "") -> str:
    """Deterministic template/rule checks for Data Vault model SQL."""

    violations = []
    lower_sql = sql.lower()

    if model_type == "staging":

        required_ctes = [
            "with src_s",
            "logic_s",
            "rename_s as",
            "filter_s as",
            "join_result",  # matches JOIN_RESULT (standard's template) and JOIN_RESULTS
            "final as",
        ]
        for cte in required_ctes:
            if cte not in lower_sql:
                violations.append(f"Missing required staging CTE: {cte}")

        if (
            "source('control', 'ref_source_system')" not in lower_sql
            and 'source("control", "ref_source_system")' not in lower_sql
        ):
            violations.append(
                "Staging must join REF_SOURCE_SYSTEM via "
                "source('control', 'REF_SOURCE_SYSTEM')."
            )

        if re.search(r"'[^']*'\s+as\s+rec_src", lower_sql):
            violations.append(
                "REC_SRC must not be hardcoded as a string literal in staging."
            )

        if re.search(r"'[^']*'\s+as\s+bkcc", lower_sql):
            violations.append(
                "BKCC must not be hardcoded as a string literal in staging."
            )

        if "md5_binary" not in lower_sql:
            violations.append("Staging must compute hash columns using MD5_BINARY.")

    elif model_type in ["hub", "link"]:

        if "ghost_records as" not in lower_sql:
            violations.append("Hub/Link must include ghost_records CTE.")

        for sentinel in [
            "md5_binary(upper('0'))",
            "md5_binary(upper('-1'))",
            "md5_binary(upper('-2'))",
        ]:
            if sentinel not in lower_sql:
                violations.append(f"Missing ghost hash sentinel: {sentinel}")

        md5_positions = [m.start() for m in re.finditer(r"md5_binary", lower_sql)]

        if md5_positions:
            ghost_idx = lower_sql.find("ghost_records as")

            if ghost_idx == -1:
                violations.append(
                    "MD5_BINARY found but ghost_records CTE is missing."
                )
            else:
                for pos in md5_positions:
                    if pos < ghost_idx:
                        violations.append(
                            "Hub/Link must not recompute business hashes "
                            "outside ghost_records."
                        )
                        break

        if "row_number() over" not in lower_sql:
            violations.append("Hub/Link must include QUALIFY ROW_NUMBER() dedup pattern.")

    elif model_type == "satellite":

        if "md5_binary" in lower_sql:
            violations.append(
                "Satellite must not compute MD5_BINARY; HASHDIFF must come from staging."
            )

        if "hashdiff" not in lower_sql:
            violations.append("Satellite must select HASHDIFF from staging.")

        if "bkcc" in lower_sql:
            violations.append("Satellite must exclude BKCC.")

        if "row_number() over" not in lower_sql:
            violations.append("Satellite must dedup with QUALIFY ROW_NUMBER().")

        if "partition by" not in lower_sql or "hashdiff" not in lower_sql:
            violations.append(
                "Satellite dedup must partition by parent _HK and HASHDIFF."
            )

    else:
        violations.append(f"Unsupported model_type: {model_type}")

    return json.dumps({"pass": len(violations) == 0, "violations": violations}, indent=2)


TOOLS = [
    {
        "name": "validate_model_tool",
        "description": (
            "Deterministically check generated Data Vault dbt model SQL "
            "against DV_STANDARD.MD rules."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "Full SQL text of the model.",
                },
                "model_type": {
                    "type": "string",
                    "enum": ["staging", "hub", "link", "satellite"],
                    "description": "Model layer.",
                },
            },
            "required": ["sql", "model_type"],
        },
    },
]

HANDLERS = {
    "validate_model_tool": validate_model,
}


if __name__ == "__main__":
    serve("dv-validator-mcp", TOOLS, HANDLERS)
