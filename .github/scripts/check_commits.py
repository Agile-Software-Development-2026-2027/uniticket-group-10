"""Checks that commit messages follow the same format as pull request titles.

With --message-file it checks one message (the commit-msg hook),
otherwise the commits between two revisions written since RULE_START (the pipeline).
"""

import subprocess
import sys

from check_pr import title_errors

# Commits written before the rule existed are not checked (author date).
RULE_START = "2026-11-01"
# Made by git itself, they disappear with the squash merge.
SKIPPED = ("Merge ", "Revert ", "fixup! ", "squash! ", "amend! ")


def subject(message):
    for line in message.splitlines():
        if line.strip() and not line.startswith("#"):
            return line.strip()
    return ""


def message_errors(message):
    first = subject(message)
    if first.startswith(SKIPPED):
        return []
    return title_errors(first, "Commit message")


def main():
    if sys.argv[1] == "--message-file":
        with open(sys.argv[2], encoding="utf-8") as stream:
            errors = message_errors(stream.read())
        for error in errors:
            print(error, file=sys.stderr)
    else:
        base, head = sys.argv[1:3]
        log = subprocess.run(
            ["git", "log", "--no-merges", "--format=%h %as %s", f"{base}..{head}"],
            capture_output=True, text=True, check=True,
        ).stdout
        errors = []
        for line in log.splitlines():
            commit, date, message = line.split(" ", 2)
            if date >= RULE_START:
                errors += [f"{commit}: {error}" for error in message_errors(message)]
        for error in errors:
            print(f"::error::{error}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
