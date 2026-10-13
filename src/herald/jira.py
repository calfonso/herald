"""Jira API interaction: authentication, ADF conversion, and field updates."""

import base64
import json
import os
from dataclasses import dataclass
from typing import Optional

import aiohttp
import pyadf


def _text_to_adf(text: str) -> dict:
    """Convert markdown text into an ADF document for Jira Cloud API v3."""
    return pyadf.Document.from_markdown(text).to_adf()


@dataclass
class JiraUpdateResult:
    ok: bool
    error: Optional[str] = None
    state: str = "published"  # "published", "rejected", or "unconfirmed"


def _normalized_adf(value):
    """Canonicalize ADF for comparing content despite JSON/mark ordering."""
    if isinstance(value, list):
        return [_normalized_adf(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, item in sorted(value.items()):
            if key == "version":
                continue
            value_normalized = _normalized_adf(item)
            # Marks have no ordering semantics; content arrays do.
            if key == "marks" and isinstance(value_normalized, list):
                value_normalized = sorted(
                    value_normalized, key=lambda mark: json.dumps(mark, sort_keys=True)
                )
            normalized[key] = value_normalized
        return normalized
    return value


async def update_jira_status(
    session: aiohttp.ClientSession,
    jira_url: str,
    auth_headers: dict,
    issue_key: str,
    status_text: str,
) -> JiraUpdateResult:
    """Set customfield_10814 on a Jira issue.

    After a successful PUT, reads the field back to verify it actually changed.
    """
    url = f"{jira_url}/rest/api/3/issue/{issue_key}"
    payload = {"fields": {"customfield_10814": _text_to_adf(status_text)}}
    try:
        async with session.put(url, json=payload, headers=auth_headers) as resp:
            if resp.status not in (200, 204):
                text = await resp.text()
                if resp.status == 403:
                    return JiraUpdateResult(
                        False,
                        f"No permission to update {issue_key} (customfield_10814). "
                        f"Check your API token has edit access.",
                        "rejected",
                    )
                return JiraUpdateResult(
                    False, f"Failed to update {issue_key}: {resp.status} {text}", "rejected"
                )
    except Exception as exc:
        return JiraUpdateResult(
            False,
            f"Could not confirm whether the update for {issue_key} reached Jira: {exc}",
            "unconfirmed",
        )

    verify_url = f"{jira_url}/rest/api/3/issue/{issue_key}?fields=customfield_10814"
    try:
        async with session.get(verify_url, headers=auth_headers) as resp:
            if resp.status not in (200, 204):
                return JiraUpdateResult(
                    False,
                    f"PUT for {issue_key} returned 204 but verify GET failed "
                    f"({resp.status}). Update may not have persisted.",
                    "unconfirmed",
                )
            data = await resp.json()
            actual = data.get("fields", {}).get("customfield_10814")
            if actual is None:
                return JiraUpdateResult(
                    False,
                    f"{issue_key} customfield_10814 is null after PUT. The field "
                    f"may not exist on this issue type or was silently rejected.",
                    "unconfirmed",
                )

            expected = _normalized_adf(payload["fields"]["customfield_10814"])
            if _normalized_adf(actual) != expected:
                return JiraUpdateResult(
                    False,
                    f"Jira accepted the update for {issue_key}, but read-back content "
                    "does not match. Publication is unconfirmed; retry after checking Jira.",
                    "unconfirmed",
                )
    except Exception as exc:
        return JiraUpdateResult(
            False,
            f"PUT for {issue_key} succeeded, but read-back failed: {exc}",
            "unconfirmed",
        )

    return JiraUpdateResult(True)


def get_jira_auth() -> dict:
    """Build Jira auth headers from JIRA_USERNAME + JIRA_API_TOKEN env vars."""
    username = os.environ.get("JIRA_USERNAME", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    if not username or not token:
        raise ValueError("JIRA_USERNAME and JIRA_API_TOKEN must be set")
    credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
