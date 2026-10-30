#!/bin/sh
# Copy the Muse Spark Open settings (OPEN_MODEL_*) into the guard agent's settings (GUARD_MODEL_*) in an env file, so the guard's
# model review runs on the same endpoint as private mode. No new account or key is needed. Rule 9: Muse Spark Open on Fireworks is a Meta model.
# It never prints a value. It replaces any existing GUARD_MODEL_API_KEY / GUARD_MODEL_BASE_URL / GUARD_MODEL_ID lines and leaves the rest alone.
#
#   Local:   sh deploy/set-guard-keys.sh .env
#   Server:  ssh -i ~/.ssh/diocle root@SERVER 'sh -s -- /opt/diocle/deploy/diocle.env' < deploy/set-guard-keys.sh
#            then restart the API:  ssh ... 'cd /opt/diocle/deploy && docker compose -f docker-compose.api.yml up -d'
set -eu
f=${1:?usage: set-guard-keys.sh ENV_FILE}
[ -f "$f" ] || { echo "set-guard-keys: no such file: $f" >&2; exit 2; }
val() { sed -n "s/^$1=//p" "$f" | tail -n 1; }
key=$(val OPEN_MODEL_API_KEY)
[ -n "$key" ] || { echo "set-guard-keys: OPEN_MODEL_API_KEY is not set in $f; nothing changed" >&2; exit 2; }
base=$(val OPEN_MODEL_BASE_URL); [ -n "$base" ] || base=https://api.fireworks.ai/inference/v1
id=$(val OPEN_MODEL_ID);         [ -n "$id" ]   || id=accounts/fireworks/models/muse-spark-open
tmp=$(mktemp "${TMPDIR:-/tmp}/guard-keys.XXXXXX"); trap 'rm -f "$tmp"' EXIT INT TERM
grep -vE '^(GUARD_MODEL_API_KEY|GUARD_MODEL_BASE_URL|GUARD_MODEL_ID)=' "$f" > "$tmp" || true
{ printf 'GUARD_MODEL_API_KEY=%s\n' "$key"; printf 'GUARD_MODEL_BASE_URL=%s\n' "$base"; printf 'GUARD_MODEL_ID=%s\n' "$id"; } >> "$tmp"
cat "$tmp" > "$f"   # same file, same owner and permissions
echo "set-guard-keys: GUARD_MODEL_* set in $f from OPEN_MODEL_* (values not shown)"
