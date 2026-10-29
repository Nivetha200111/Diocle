#!/bin/sh
# Updates the engine on the server to the latest main and checks it came back. Run it from the machine that holds
# the SSH key (see docs/HANDOFF.md). Rebuilding restarts the api and kills a running delivery, so it refuses while
# one is running; FORCE=1 overrides.
# Usage: deploy/update-engine.sh [root@SERVER_IP]
set -eu
HOST=${1:-root@65.20.92.159}
KEY=${SSH_KEY:-$HOME/.ssh/diocle}
API=${API:-https://diocle.vercel.app/api}

echo "Checking for a running delivery…"
running=$(curl -fsS "$API/deliveries" | python3 -c 'import json, sys
print(" ".join(d["id"] for d in json.load(sys.stdin) if d["stage"] not in ("done", "failed")))')
if [ -n "$running" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "A delivery is running ($running); updating now would kill it. Try again later, or FORCE=1 $0" >&2
  exit 1
fi

echo "Updating $HOST…"
ssh -i "$KEY" "$HOST" 'set -e
cd /opt/diocle
git pull --ff-only
git log --oneline -1
cd deploy
docker compose -f docker-compose.api.yml up -d --build'

echo "Waiting for the api…"
i=0
until curl -fsS -o /dev/null "$API/health"; do
  i=$((i + 1))
  [ "$i" -lt 60 ] || { echo "The api did not come back in 5 minutes; check: docker compose -f docker-compose.api.yml logs api" >&2; exit 1; }
  sleep 5
done

code=$(curl -s -o /dev/null -w '%{http_code}' "$API/runs/chqclr-20261028-214355/source")
if [ "$code" = 200 ]; then
  echo "Done: the engine is up and serves sources. The front page now shows the Java next to the COBOL."
else
  echo "The api is up, but GET /runs/{id}/source answered $code (expected 200). Is the server on the latest main?" >&2
  exit 1
fi
