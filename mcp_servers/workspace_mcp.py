# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""
Workspace MCP server  (registered as "workspace-mcp")

Tools:
  read_file_tool   read one file from the project (read-only)
  run_commands     run a shell command in the project folder (dbt, git, gh)
  execute_git_pr   stage ONLY the given files, commit, push and open a GitHub PR

Used by: dv-model-generator and dv-code-reviewer (read_file_tool).
run_commands / execute_git_pr are available as a scripted alternative to the
terminal steps in the Coordinator and dv-pr-generator.

All paths are relative to the project root (the folder holding mcp_servers/),
or to $DV_WORKSPACE if that environment variable is set.
"""

import json
import os
import re
import subprocess

from mcp_base import PROJECT_ROOT, serve

WORKSPACE = os.environ.get("DV_WORKSPACE", PROJECT_ROOT)
DEFAULT_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "300"))


# ============================================================
# READ FILE
# ============================================================

def read_file(file_path: str = "") -> str:
    full_path = os.path.join(WORKSPACE, file_path)

    if os.path.isfile(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    return f"Error: File not found at {full_path}"


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_commands(command: str = "", cwd=None, timeout=None) -> str:
    """Execute a workspace command (git, dbt, gh, ...)."""

    if not command or not command.strip():
        raise ValueError("Command cannot be empty.")

    working_directory = cwd or WORKSPACE
    if not os.path.isdir(working_directory):
        raise RuntimeError(f"Workspace does not exist: {working_directory}")

    timeout = timeout or DEFAULT_TIMEOUT

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = completed.stdout or ""
        if completed.stderr:
            output = f"{output}\n{completed.stderr}" if output else completed.stderr

        return json.dumps({
            "success": completed.returncode == 0,
            "exit_code": completed.returncode,
            "command": command,
            "cwd": working_directory,
            "output": output.strip(),
        }, indent=2)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "exit_code": -1,
            "command": command,
            "cwd": working_directory,
            "error": f"Command timed out after {timeout} seconds.",
        }, indent=2)


# ============================================================
# GIT / GITHUB PR
# ============================================================

def _run(cmd, label):
    result = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def _run_git(args):
    return _run(["git"] + args, f"git {' '.join(args)}")


def _validate_branch_name(branch_name):
    if not branch_name:
        raise ValueError("branch_name is required.")
    if not re.match(r"^[A-Za-z0-9._/-]+$", branch_name):
        raise ValueError(f"Invalid branch name: {branch_name}")


def _validate_file_path(file_path):
    if not file_path:
        raise ValueError("File paths cannot be empty.")

    normalized = file_path.replace("\\", "/")

    if os.path.isabs(normalized):
        raise ValueError(f"Absolute file paths are not allowed: {file_path}")
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError(f"Parent-directory file paths are not allowed: {file_path}")


def run_git_pr(branch_name=None, pr_title=None, pr_body=None, files=None) -> str:
    """Stage only the exact files, commit, push the branch and create a PR."""

    files = files or []

    _validate_branch_name(branch_name)
    if not pr_title:
        raise ValueError("pr_title is required.")
    if not files:
        raise ValueError("At least one generated file is required.")
    for file_path in files:
        _validate_file_path(file_path)

    current_branch = _run_git(["branch", "--show-current"])
    if current_branch != branch_name:
        raise RuntimeError(
            f"Current branch is '{current_branch}', but expected '{branch_name}'."
        )

    missing = [f for f in files if not os.path.isfile(os.path.join(WORKSPACE, f))]
    if missing:
        raise RuntimeError(
            "The following generated files do not exist:\n" + "\n".join(missing)
        )

    # Stage ONLY the exact files
    _run_git(["add", "--"] + files)

    # --relative: report paths relative to this project folder, so the check
    # below also works when the project lives in a subfolder of a monorepo.
    staged = _run_git(["diff", "--cached", "--name-only", "--relative"])
    staged_files = [line.strip() for line in staged.splitlines() if line.strip()]

    if not staged_files:
        raise RuntimeError("No changes were staged. PR creation stopped.")

    normalized_files = {f.replace("\\", "/") for f in files}
    unexpected = sorted(set(staged_files) - normalized_files)
    if unexpected:
        raise RuntimeError("Unexpected files were staged:\n" + "\n".join(unexpected))

    commit_message = pr_title.strip()
    _run(["git", "commit", "-m", commit_message], "Git commit")
    _run(["git", "push", "-u", "origin", branch_name], "Git push")

    pr_url = _run(
        [
            "gh", "pr", "create",
            "--base", "main",
            "--head", branch_name,
            "--title", pr_title,
            "--body", pr_body or "",
        ],
        "GitHub PR creation",
    )

    return json.dumps({
        "success": True,
        "branch": branch_name,
        "staged_files": staged_files,
        "commit": commit_message,
        "pr_url": pr_url,
    }, indent=2)


# ============================================================
# MCP REGISTRATION
# ============================================================

TOOLS = [
    {
        "name": "read_file_tool",
        "description": "Read the contents of a specific file from the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path relative to the project root "
                        "(e.g. '.github/agents/DV_STANDARD.MD')."
                    ),
                }
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "run_commands",
        "description": (
            "Execute a command in the project workspace "
            "(dbt build, git, gh, other approved commands)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute."},
                "cwd": {"type": "string", "description": "Optional working directory."},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds.",
                    "default": DEFAULT_TIMEOUT,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "execute_git_pr",
        "description": (
            "Stages only the specified files, commits them, pushes the "
            "current branch, and creates a GitHub pull request."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch_name": {"type": "string", "description": "Expected current Git branch."},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact files to stage, relative to the project root.",
                },
                "pr_title": {"type": "string", "description": "Commit message and PR title."},
                "pr_body": {"type": "string", "description": "Pull request body."},
            },
            "required": ["branch_name", "files", "pr_title", "pr_body"],
        },
    },
]

HANDLERS = {
    "read_file_tool": read_file,
    "run_commands": run_commands,
    "execute_git_pr": run_git_pr,
}


if __name__ == "__main__":
    serve("workspace-mcp", TOOLS, HANDLERS)
