#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Un solo Compose per l’intero prototipo.
compose_files=(-f compose.yml)
startup_log=$(mktemp)
trap 'rm -f -- "$startup_log"' EXIT
if ! docker compose "${compose_files[@]}" up --build -d >"$startup_log" 2>&1; then
    cat "$startup_log" >&2
    exit 1
fi
# Show recent receiver records and continue following new events.
docker compose "${compose_files[@]}" logs --follow --tail 150 --no-log-prefix lab |
    awk '/^\[TICKET EVENT\] \{$/ { inside=1 }
         inside { print; fflush() }
         inside && /^}$/ { inside=0; print ""; fflush() }' 
