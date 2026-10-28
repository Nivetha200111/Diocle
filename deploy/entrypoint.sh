#!/bin/sh
# Lets git push with the fine-grained token in GH_TOKEN (delivery branches), then serves the API.
set -e
if [ -n "$GH_TOKEN" ]; then
  gh auth setup-git >/dev/null 2>&1 || true
  git config --global user.name "Diocle"
  git config --global user.email "diocle@users.noreply.github.com"
fi
mkdir -p /srv/diocle/runs
cd /srv/diocle/services/api
exec .venv/bin/uvicorn diocle_api.app:app --host 0.0.0.0 --port 8000 --proxy-headers
