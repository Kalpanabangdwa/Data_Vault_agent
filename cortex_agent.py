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

from dotenv import load_dotenv
from snowflake.connector import connect


load_dotenv()

_snowflake_conn = None


# ============================================================
# CONFIGURATION
# ============================================================

WORKSPACE = os.environ.get("DV_WORKSPACE", os.getcwd())
DEFAULT_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "300"))


# ============================================================
# SNOWFLAKE
# ============================================================

def run_sql_query(query):
    """
    Execute SQL against Snowflake.

    Intended for metadata/schema/control-table queries used by
    the agent workflow.
    """

    global _snowflake_conn

    try:
        if _snowflake_conn is None or _snowflake_conn.is_closed():
            _snowflake_conn = connect(
                account=os.environ["SNOWFLAKE_ACCOUNT"],
                user=os.environ["SNOWFLAKE_USER"],
                password=os.environ["SNOWFLAKE_PASSWORD"],
                warehouse=os.environ.get(
                    "SNOWFLAKE_WAREHOUSE",
                    "COMPUTE_WH"
                ),
                database=os.environ.get(
                    "SNOWFLAKE_DATABASE",
                    "CUSTOM_AGENT"
                ),
                schema=os.environ.get(
                    "SNOWFLAKE_SCHEMA",
                    "STAGING"
                )
            )

        cursor = _snowflake_conn.cursor()

        try:
            cursor.execute(query)

            # SELECT / SHOW / DESCRIBE style queries
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()

                result = [
                    dict(zip(columns, row))
                    for row in rows
                ]

                return json.dumps(
                    result,
                    default=str,
                    indent=2
                )

            # DDL / commands that don't return rows
            return json.dumps({
                "success": True,
                "rowcount": cursor.rowcount
            })

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


# ============================================================
# MODEL VALIDATION
# ============================================================

def validate_model(sql: str, model_type: str) -> str:
    """
    Performs deterministic template/rule checks for
    Data Vault model SQL.
    """

    violations = []
    lower_sql = sql.lower()

    if model_type == "staging":

        required_ctes = [
            "with src as",
            "logic as",
            "rename as",
            "filter as",
            "join_layer as",
            "final as"
        ]

        for cte in required_ctes:
            if cte not in lower_sql:
                violations.append(
                    f"Missing required staging CTE: {cte}"
                )

        if (
            "source('control', 'ref_source_system')" not in lower_sql
            and
            'source("control", "ref_source_system")' not in lower_sql
        ):
            violations.append(
                "Staging must join REF_SOURCE_SYSTEM via "
                "source('control', 'REF_SOURCE_SYSTEM')."
            )

        if re.search(
            r"'[^']*'\s+as\s+rec_src",
            lower_sql
        ):
            violations.append(
                "REC_SRC must not be hardcoded as a "
                "string literal in staging."
            )

        if re.search(
            r"'[^']*'\s+as\s+bkcc",
            lower_sql
        ):
            violations.append(
                "BKCC must not be hardcoded as a "
                "string literal in staging."
            )

        if "md5_binary" not in lower_sql:
            violations.append(
                "Staging must compute hash columns using MD5_BINARY."
            )

    elif model_type in ["hub", "link"]:

        if "ghost_records as" not in lower_sql:
            violations.append(
                "Hub/Link must include ghost_records CTE."
            )

        for sentinel in [
            "md5_binary(upper('0'))",
            "md5_binary(upper('-1'))",
            "md5_binary(upper('-2'))"
        ]:
            if sentinel not in lower_sql:
                violations.append(
                    f"Missing ghost hash sentinel: {sentinel}"
                )

        md5_positions = [
            m.start()
            for m in re.finditer(
                r"md5_binary",
                lower_sql
            )
        ]

        if md5_positions:

            ghost_idx = lower_sql.find(
                "ghost_records as"
            )

            if ghost_idx == -1:
                violations.append(
                    "MD5_BINARY found but ghost_records "
                    "CTE is missing."
                )
            else:
                for pos in md5_positions:
                    if pos < ghost_idx:
                        violations.append(
                            "Hub/Link must not recompute "
                            "business hashes outside ghost_records."
                        )
                        break

        if "row_number() over" not in lower_sql:
            violations.append(
                "Hub/Link must include QUALIFY "
                "ROW_NUMBER() dedup pattern."
            )

    elif model_type == "satellite":

        if "md5_binary" in lower_sql:
            violations.append(
                "Satellite must not compute MD5_BINARY; "
                "HASHDIFF must come from staging."
            )

        if "hashdiff" not in lower_sql:
            violations.append(
                "Satellite must select HASHDIFF from staging."
            )

        if "bkcc" in lower_sql:
            violations.append(
                "Satellite must exclude BKCC."
            )

        if "row_number() over" not in lower_sql:
            violations.append(
                "Satellite must dedup with "
                "QUALIFY ROW_NUMBER()."
            )

        if (
            "partition by" not in lower_sql
            or
            "hashdiff" not in lower_sql
        ):
            violations.append(
                "Satellite dedup must partition by "
                "parent _HK and HASHDIFF."
            )

    else:
        violations.append(
            f"Unsupported model_type: {model_type}"
        )

    result = {
        "pass": len(violations) == 0,
        "violations": violations
    }

    return json.dumps(result, indent=2)


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_commands(command, cwd=None, timeout=None):
    """
    Execute a workspace command for the agent workflow.

    Used for:
      - git
      - dbt
      - gh
      - other approved project commands

    The command is executed from the configured workspace.
    """

    if not command or not command.strip():
        raise ValueError("Command cannot be empty.")

    working_directory = cwd or WORKSPACE

    if not os.path.isdir(working_directory):
        raise RuntimeError(
            f"Workspace does not exist: {working_directory}"
        )

    timeout = timeout or DEFAULT_TIMEOUT

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = ""

        if completed.stdout:
            output += completed.stdout

        if completed.stderr:
            if output:
                output += "\n"
            output += completed.stderr

        result = {
            "success": completed.returncode == 0,
            "exit_code": completed.returncode,
            "command": command,
            "cwd": working_directory,
            "output": output.strip()
        }

        return json.dumps(result, indent=2)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "exit_code": -1,
            "command": command,
            "cwd": working_directory,
            "error": f"Command timed out after {timeout} seconds."
        }, indent=2)


# ============================================================
# GIT / GITHUB PR
# ============================================================

def _run_git(args):
    """
    Execute git safely using argument arrays.
    """

    result = subprocess.run(
        ["git"] + args,
        cwd=WORKSPACE,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n"
            f"{result.stdout}\n"
            f"{result.stderr}"
        )

    return result.stdout.strip()


def _validate_branch_name(branch_name):
    if not branch_name:
        raise ValueError("branch_name is required.")

    if not re.match(
        r"^[A-Za-z0-9._/-]+$",
        branch_name
    ):
        raise ValueError(
            f"Invalid branch name: {branch_name}"
        )


def _validate_file_path(file_path):
    if not file_path:
        raise ValueError(
            "File paths cannot be empty."
        )

    normalized = file_path.replace("\\", "/")

    if os.path.isabs(normalized):
        raise ValueError(
            f"Absolute file paths are not allowed: {file_path}"
        )

    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError(
            f"Parent-directory file paths are not allowed: {file_path}"
        )


def run_git_pr(
    branch_name,
    pr_title,
    pr_body,
    files
):
    """
    Stage only the exact generated files, commit them,
    push the branch and create a GitHub PR.
    """

    _validate_branch_name(branch_name)

    if not pr_title:
        raise ValueError("pr_title is required.")

    if not files:
        raise ValueError(
            "At least one generated file is required."
        )

    for file_path in files:
        _validate_file_path(file_path)

    # --------------------------------------------------------
    # Verify current branch
    # --------------------------------------------------------

    current_branch = _run_git(
        ["branch", "--show-current"]
    )

    if current_branch != branch_name:
        raise RuntimeError(
            f"Current branch is '{current_branch}', "
            f"but expected '{branch_name}'."
        )

    # --------------------------------------------------------
    # Verify generated files exist
    # --------------------------------------------------------

    missing_files = []

    for file_path in files:
        full_path = os.path.join(
            WORKSPACE,
            file_path
        )

        if not os.path.isfile(full_path):
            missing_files.append(file_path)

    if missing_files:
        raise RuntimeError(
            "The following generated files do not exist:\n"
            + "\n".join(missing_files)
        )

    # --------------------------------------------------------
    # Stage ONLY exact files
    # --------------------------------------------------------

    _run_git(
        ["add", "--"] + files
    )

    # --------------------------------------------------------
    # Check staged changes
    # --------------------------------------------------------

    staged = _run_git(
        ["diff", "--cached", "--name-only"]
    )

    staged_files = [
        line.strip()
        for line in staged.splitlines()
        if line.strip()
    ]

    if not staged_files:
        raise RuntimeError(
            "No changes were staged. "
            "PR creation stopped."
        )

    unexpected = sorted(
        set(staged_files) - set(files)
    )

    if unexpected:
        raise RuntimeError(
            "Unexpected files were staged:\n"
            + "\n".join(unexpected)
        )

    # --------------------------------------------------------
    # Commit
    # --------------------------------------------------------

    commit_message = pr_title.strip()

    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=WORKSPACE,
        capture_output=True,
        text=True
    )

    if commit_result.returncode != 0:
        raise RuntimeError(
            "Git commit failed:\n"
            + commit_result.stdout
            + "\n"
            + commit_result.stderr
        )

    # --------------------------------------------------------
    # Push
    # --------------------------------------------------------

    push_result = subprocess.run(
        [
            "git",
            "push",
            "-u",
            "origin",
            branch_name
        ],
        cwd=WORKSPACE,
        capture_output=True,
        text=True
    )

    if push_result.returncode != 0:
        raise RuntimeError(
            "Git push failed:\n"
            + push_result.stdout
            + "\n"
            + push_result.stderr
        )

    # --------------------------------------------------------
    # Create GitHub PR
    # --------------------------------------------------------

    pr_result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch_name,
            "--title",
            pr_title,
            "--body",
            pr_body or ""
        ],
        cwd=WORKSPACE,
        capture_output=True,
        text=True
    )

    if pr_result.returncode != 0:
        raise RuntimeError(
            "GitHub PR creation failed:\n"
            + pr_result.stdout
            + "\n"
            + pr_result.stderr
        )

    pr_url = pr_result.stdout.strip()

    return json.dumps({
        "success": True,
        "branch": branch_name,
        "staged_files": staged_files,
        "commit": commit_message,
        "pr_url": pr_url
    }, indent=2)


# ============================================================
# MCP SERVER
# ============================================================

def handle_input():

    for line in sys.stdin:

        if not line.strip():
            continue

        req = {}

        try:

            req = json.loads(line)

            method = req.get("method")
            req_id = req.get("id")

            # =================================================
            # INITIALIZE
            # =================================================

            if method == "initialize":

                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "cortex-mcp-server",
                            "version": "2.0.0"
                        }
                    }
                }

                sys.stdout.write(
                    json.dumps(response) + "\n"
                )
                sys.stdout.flush()

                continue

            # =================================================
            # LIST TOOLS
            # =================================================

            if method == "tools/list":

                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [

                            # ---------------------------------
                            # SNOWFLAKE
                            # ---------------------------------

                            {
                                "name": "sql_exec_tool",
                                "description": (
                                    "Execute SQL queries against "
                                    "the configured Snowflake database."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": (
                                                "Exact SQL string "
                                                "to execute."
                                            )
                                        }
                                    },
                                    "required": ["query"]
                                }
                            },

                            # ---------------------------------
                            # VALIDATION
                            # ---------------------------------

                            {
                                "name": "validate_model_tool",
                                "description": (
                                    "Deterministically check generated "
                                    "Data Vault dbt model SQL against "
                                    "DV_STANDARD.md rules."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "sql": {
                                            "type": "string",
                                            "description": (
                                                "Full SQL text of "
                                                "the model."
                                            )
                                        },
                                        "model_type": {
                                            "type": "string",
                                            "enum": [
                                                "staging",
                                                "hub",
                                                "link",
                                                "satellite"
                                            ],
                                            "description": (
                                                "Model layer."
                                            )
                                        }
                                    },
                                    "required": [
                                        "sql",
                                        "model_type"
                                    ]
                                }
                            },

                            # ---------------------------------
                            # COMMAND EXECUTION
                            # ---------------------------------

                            {
                                "name": "run_commands",
                                "description": (
                                    "Execute a command in the "
                                    "configured Data Vault workspace. "
                                    "Used by the Coordinator for "
                                    "dbt validation/build and by "
                                    "agents for approved workspace "
                                    "operations."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": (
                                                "Command to execute."
                                            )
                                        },
                                        "cwd": {
                                            "type": "string",
                                            "description": (
                                                "Optional working "
                                                "directory."
                                            )
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": (
                                                "Timeout in seconds."
                                            ),
                                            "default": 300
                                        }
                                    },
                                    "required": ["command"]
                                }
                            },

                            # ---------------------------------
                            # GIT + GITHUB PR
                            # ---------------------------------

                            {
                                "name": "execute_git_pr",
                                "description": (
                                    "Stages only the specified "
                                    "generated files, commits them, "
                                    "pushes the current branch, and "
                                    "creates a GitHub pull request."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {

                                        "branch_name": {
                                            "type": "string",
                                            "description": (
                                                "Expected current "
                                                "Git branch."
                                            )
                                        },

                                        "files": {
                                            "type": "array",
                                            "items": {
                                                "type": "string"
                                            },
                                            "description": (
                                                "Exact generated "
                                                "files to stage."
                                            )
                                        },

                                        "pr_title": {
                                            "type": "string",
                                            "description": (
                                                "Git commit and "
                                                "pull request title."
                                            )
                                        },

                                        "pr_body": {
                                            "type": "string",
                                            "description": (
                                                "Pull request body."
                                            )
                                        }

                                    },
                                    "required": [
                                        "branch_name",
                                        "files",
                                        "pr_title",
                                        "pr_body"
                                    ]
                                }
                            }

                        ]
                    }
                }

                sys.stdout.write(
                    json.dumps(response) + "\n"
                )
                sys.stdout.flush()

                continue

            # =================================================
            # CALL TOOL
            # =================================================

            if method == "tools/call":

                params = req.get(
                    "params",
                    {}
                )

                tool_name = params.get("name")

                arguments = params.get(
                    "arguments",
                    {}
                )

                # ---------------------------------------------
                # Snowflake
                # ---------------------------------------------

                if tool_name == "sql_exec_tool":

                    query = arguments.get(
                        "query"
                    )

                    if not query:
                        raise ValueError(
                            "query is required."
                        )

                    output_text = run_sql_query(
                        query
                    )

                # ---------------------------------------------
                # Validator
                # ---------------------------------------------

                elif tool_name == "validate_model_tool":

                    output_text = validate_model(
                        sql=arguments.get(
                            "sql",
                            ""
                        ),
                        model_type=arguments.get(
                            "model_type",
                            ""
                        )
                    )

                # ---------------------------------------------
                # Commands
                # ---------------------------------------------

                elif tool_name == "run_commands":

                    output_text = run_commands(
                        command=arguments.get(
                            "command",
                            ""
                        ),
                        cwd=arguments.get(
                            "cwd"
                        ),
                        timeout=arguments.get(
                            "timeout",
                            DEFAULT_TIMEOUT
                        )
                    )

                # ---------------------------------------------
                # Git + PR
                # ---------------------------------------------

                elif tool_name == "execute_git_pr":

                    output_text = run_git_pr(
                        branch_name=arguments.get(
                            "branch_name"
                        ),
                        files=arguments.get(
                            "files",
                            []
                        ),
                        pr_title=arguments.get(
                            "pr_title"
                        ),
                        pr_body=arguments.get(
                            "pr_body"
                        )
                    )

                else:

                    raise ValueError(
                        f"Unknown tool name '{tool_name}'"
                    )

                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": output_text
                            }
                        ]
                    }
                }

                sys.stdout.write(
                    json.dumps(response) + "\n"
                )
                sys.stdout.flush()

                continue

        except Exception as e:

            err_resp = {
                "jsonrpc": "2.0",
                "id": (
                    req.get("id", 0)
                    if isinstance(req, dict)
                    else 0
                ),
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

            sys.stdout.write(
                json.dumps(err_resp) + "\n"
            )

            sys.stdout.flush()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    handle_input()