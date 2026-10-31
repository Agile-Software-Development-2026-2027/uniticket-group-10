"""Checks that the title and the body of a pull request follow the team format.

Reads them from the PR_TITLE and PR_BODY environment variables.
"""

import os
import re
import sys

TITLE = re.compile(r"(SCRUM-[1-9][0-9]*) [A-Z].*[^.\s]")
MAX_TITLE_LENGTH = 72
SECTIONS = ["What changed", "How to check"]


def title_errors(title, kind="Title"):
    if TITLE.fullmatch(title) and len(title) <= MAX_TITLE_LENGTH:
        return []
    return [
        f'{kind} "{title}" is not valid. Expected "SCRUM-12 Add the login form": '
        f"Jira key, one space, a capitalized description, no final period, "
        f"at most {MAX_TITLE_LENGTH} characters."
    ]


def sections(body):
    found = {}
    name = None
    for line in body.splitlines():
        if line.startswith("## "):
            name = line[3:].strip().lower()
            found[name] = ""
        elif name:
            found[name] += line
    return found


def body_errors(body, key):
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    errors = []
    jira = re.search(r"^Jira issue:(.*)$", body, flags=re.MULTILINE)
    pattern = re.escape(key) if key else r"SCRUM-[1-9][0-9]*"
    if not jira or not re.search(rf"\b{pattern}\b", jira.group(1)):
        expected = key or "the Jira key"
        errors.append(f'The line "Jira issue:" must contain {expected}.')
    found = sections(body)
    for name in SECTIONS:
        content = found.get(name.lower())
        if content is None:
            errors.append(f'Section "## {name}" is missing.')
        elif not content.strip():
            errors.append(f'Section "## {name}" is empty.')
    return errors


def main():
    title = os.environ.get("PR_TITLE", "").strip()
    body = os.environ.get("PR_BODY", "")
    match = TITLE.match(title)
    key = match.group(1) if match else None
    errors = title_errors(title) + body_errors(body, key)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        sys.exit(1)
    print("Title and body follow the format.")


if __name__ == "__main__":
    main()
