#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
startup_log=$(mktemp)
trap 'rm -f -- "$startup_log"' EXIT
if ! docker compose -f compose.receiver-demo.yml up --build -d >"$startup_log" 2>&1; then
    cat "$startup_log" >&2
    exit 1
fi
# Show recent receiver records and continue following new events.
docker compose -f compose.receiver-demo.yml logs --follow --tail 150 --no-log-prefix lab |
    awk '/^\[TICKET EVENT\] \{$/ { inside=1 }
         inside { print; fflush() }
         inside && /^}$/ { inside=0; print ""; fflush() }' 
