"""Checks that commit messages follow Conventional Commits, for example "feat: add the login form".

With --message-file it checks one message and fails (the commit-msg hook). Otherwise it only
warns about the commits between two revisions written since RULE_START (the pipeline): with the
squash merge only the pull request title reaches main, and that one is checked by check_pr.py.
"""

import re
import subprocess
import sys

TYPES = ["build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test"]
MESSAGE = re.compile(rf"({'|'.join(TYPES)})(\([\w-]+\))?!?: \S.*")
MAX_LENGTH = 72
# Commits written before the rule existed get no warning (author date).
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
    if first.startswith(SKIPPED) or (MESSAGE.fullmatch(first) and len(first) <= MAX_LENGTH):
        return []
    return [
        f'Commit message "{first}" is not valid. Expected a Conventional Commit such as '
        f'"feat: add the login form" or "fix(api): reject empty queries": a type '
        f"({', '.join(TYPES)}), an optional scope, a colon, a space and a description, "
        f"at most {MAX_LENGTH} characters."
    ]


def main():
    if sys.argv[1] == "--message-file":
        with open(sys.argv[2], encoding="utf-8") as stream:
            errors = message_errors(stream.read())
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            sys.exit(1)
    else:
        base, head = sys.argv[1:3]
        log = subprocess.run(
            ["git", "log", "--no-merges", "--format=%h %as %s", f"{base}..{head}"],
            capture_output=True, text=True, check=True,
        ).stdout
        for line in log.splitlines():
            commit, date, message = line.split(" ", 2)
            if date >= RULE_START:
                for error in message_errors(message):
                    print(f"::warning::{commit}: {error}")


if __name__ == "__main__":
    main()
