# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "python-dotenv",
# ]
# ///

"""
OPTIONAL Jira MCP server  (registered as "jira-mcp")

Tools:
  fetch_jira_ticket    read a ticket's summary, status and description
  add_jira_comment     post a comment on a ticket
  update_jira_status   move a ticket to another status

Used by: jira-ticket-agent only. The core Data Vault pipeline does not need
this server; teams without Jira can leave it stopped.

Credentials come from .env in the project root:
  JIRA_DOMAIN      e.g. https://your-company.atlassian.net
  JIRA_EMAIL       Atlassian account email
  JIRA_API_TOKEN   Atlassian API token (https://id.atlassian.com/manage-profile/security/api-tokens)
"""

import json
import os

import requests
from dotenv import load_dotenv

from mcp_base import ENV_FILE, serve

load_dotenv(ENV_FILE, override=True)

TIMEOUT = 10

MISSING_CREDS = (
    "Error: Jira credentials (JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN) "
    "are missing from the environment."
)


def _jira_config():
    domain = os.environ.get("JIRA_DOMAIN")
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")

    if not all([domain, email, token]):
        return None
    return domain.rstrip("/"), (email, token)


def _not_found(ticket_id):
    return f"Error: Ticket {ticket_id} not found. Check the ticket ID and your permissions."


def fetch_jira_ticket(ticket_id: str = "") -> str:
    """Fetch the summary, status and description of a Jira ticket."""
    config = _jira_config()
    if config is None:
        return MISSING_CREDS
    domain, auth = config

    try:
        response = requests.get(
            f"{domain}/rest/api/2/issue/{ticket_id}",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if response.status_code == 404:
            return _not_found(ticket_id)
        response.raise_for_status()

        data = response.json()
        fields = data.get("fields", {})

        return json.dumps({
            "ticket_id": data.get("key"),
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", "Unknown"),
            "description": fields.get("description") or "No description provided.",
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return f"Jira API Request Failed: {e}"


def add_jira_comment(ticket_id: str = "", comment: str = "") -> str:
    """Post a comment to a Jira ticket."""
    config = _jira_config()
    if config is None:
        return MISSING_CREDS
    domain, auth = config

    try:
        response = requests.post(
            f"{domain}/rest/api/2/issue/{ticket_id}/comment",
            auth=auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"body": comment},
            timeout=TIMEOUT,
        )
        if response.status_code == 404:
            return _not_found(ticket_id)
        response.raise_for_status()

        return json.dumps({
            "ticket_id": ticket_id,
            "comment_id": response.json().get("id"),
            "body": comment,
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return f"Jira API Request Failed: {e}"


def update_jira_status(ticket_id: str = "", status_name: str = "") -> str:
    """
    Transition a Jira ticket to the given status name (e.g. "In Progress"),
    matched case-insensitively against the ticket's available transitions.
    """
    config = _jira_config()
    if config is None:
        return MISSING_CREDS
    domain, auth = config

    url = f"{domain}/rest/api/2/issue/{ticket_id}/transitions"

    try:
        list_response = requests.get(
            url, auth=auth, headers={"Accept": "application/json"}, timeout=TIMEOUT
        )
        if list_response.status_code == 404:
            return _not_found(ticket_id)
        list_response.raise_for_status()

        transitions = list_response.json().get("transitions", [])
        wanted = status_name.lower()
        match = next(
            (
                t for t in transitions
                if t.get("to", {}).get("name", "").lower() == wanted
                or t.get("name", "").lower() == wanted
            ),
            None,
        )

        if match is None:
            available = [t.get("to", {}).get("name", t.get("name")) for t in transitions]
            return (
                f"Error: No transition to '{status_name}' available for "
                f"{ticket_id}. Available: {available}"
            )

        post_response = requests.post(
            url,
            auth=auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"transition": {"id": match.get("id")}},
            timeout=TIMEOUT,
        )
        post_response.raise_for_status()

        return json.dumps({
            "ticket_id": ticket_id,
            "new_status": match.get("to", {}).get("name", status_name),
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return f"Jira API Request Failed: {e}"


_TICKET_ID = {"type": "string", "description": "The Jira issue key (e.g. DLJ25-144)."}

TOOLS = [
    {
        "name": "fetch_jira_ticket",
        "description": "Fetch the summary, status and description of a Jira ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": _TICKET_ID},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "add_jira_comment",
        "description": "Post a comment to a Jira ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": _TICKET_ID,
                "comment": {"type": "string", "description": "The comment text to post."},
            },
            "required": ["ticket_id", "comment"],
        },
    },
    {
        "name": "update_jira_status",
        "description": "Transition a Jira ticket to a new status (e.g. New, In Progress, Review).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": _TICKET_ID,
                "status_name": {"type": "string", "description": "Target status name."},
            },
            "required": ["ticket_id", "status_name"],
        },
    },
]

HANDLERS = {
    "fetch_jira_ticket": fetch_jira_ticket,
    "add_jira_comment": add_jira_comment,
    "update_jira_status": update_jira_status,
}


if __name__ == "__main__":
    serve("jira-mcp", TOOLS, HANDLERS)
