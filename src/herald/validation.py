"""Validation for status drafts before review and publication."""

import re
from typing import Optional


_STATUS_LINE = re.compile(
    r"^\s*\*\s+Color Status:\s*(Red|Yellow|Green)\s*$", re.IGNORECASE
)


def validate_draft(draft: str) -> tuple[Optional[str], Optional[str]]:
    """Return (color, error); require one explicit R/Y/G status and draft body."""
    if not isinstance(draft, str) or not draft.strip():
        return None, "Draft is empty. Edit it or refresh to generate a new draft."
    matches = [
        match.group(1).title()
        for line in draft.splitlines()
        if (match := _STATUS_LINE.match(line))
    ]
    if len(matches) != 1:
        return None, "Draft must contain exactly one '* Color Status: Red/Yellow/Green' line. Edit or refresh it."
    first_line = next((line for line in draft.splitlines() if line.strip()), "")
    if not _STATUS_LINE.match(first_line):
        return None, "Draft must start with its Color Status line. Edit or refresh it."
    body = [
        line.strip()
        for line in draft.splitlines()
        if not _STATUS_LINE.match(line) and line.strip()
    ]
    if not body:
        return None, "Draft has a status but no update text. Add the update or refresh the draft."
    return matches[0], None
