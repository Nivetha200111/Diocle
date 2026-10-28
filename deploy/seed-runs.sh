#!/bin/sh
# Copies the runs worth showing to the server's runs volume: runs certified under the current verifier
# (IBM TRUNC/DISPLAY defaults, from 2026-10-28 19:00 on), their deliveries, and fix memory. Older runs were
# certified under a superseded oracle and would fail a visitor's re-verify, so they stay on the laptop.
# Usage: deploy/seed-runs.sh root@SERVER_IP
set -eu
HOST=$1
cd "$(dirname "$0")/../runs"
SINCE=${SINCE:-20261028-1900}
RUNS=$(for d in */; do d=${d%/}; ts=$(echo "$d" | grep -oE '[0-9]{8}-[0-9]{6}$' || true)
  [ -n "$ts" ] && [ -f "$d/run.json" ] && [ "${ts%??}" \> "$SINCE" ] && echo "$d"; done)
DELIVERIES=$(ls deliveries 2>/dev/null | grep -E '^delivery-' | while read d; do ts=${d#delivery-}; [ "${ts%??}" \> "$SINCE" ] && echo "deliveries/$d"; done)
tar czf - $RUNS $DELIVERIES memory.json 2>/dev/null | ssh -i "${SSH_KEY:-$HOME/.ssh/diocle}" "$HOST" \
  "docker run --rm -i -v deploy_diocle-runs:/runs alpine sh -c 'tar xzf - -C /runs && chown -R 10001:10001 /runs'"
echo "Seeded $(echo "$RUNS" | wc -w | tr -d ' ') runs and $(echo "$DELIVERIES" | wc -w | tr -d ' ') deliveries to $HOST"
