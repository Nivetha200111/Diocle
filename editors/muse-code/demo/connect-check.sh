#!/bin/sh
# Prove Muse Code connects to the installed Diocle plugin's MCP server. No model, no key, no cost (echo provider).
# Prints the plugin status, then the MCP handshake and capability-discovery lines Muse Code itself logged.
set -eu
MUSE=${MUSE:-muse}
LOGDIR=${XDG_DATA_HOME:-$HOME/.local/share}/muse/local-tracing/bootstrap
"$MUSE" plugins inspect diocle 2>&1 | sed -n '1p;3p' | sed 's/[[:space:]]cache=.*//'
START=$(date +%s)
"$MUSE" exec --provider echo --no-session-log "connect check" 2>&1 | grep '^echo:' || true
sleep 1
LOG=$(ls -t "$LOGDIR"/cli-*.log | head -1)
grep -h -E 'event="mcp\.(transport\.startup|handshake|capability\.discovery)"' "$LOG" | while IFS= read -r line; do
  printf '%s\n' "$line" | grep -o -E 'event="[^"]+"|server="[^"]+"|outcome="[^"]+"|tool_count=[0-9]+|resource_count=[0-9]+|prompt_count=[0-9]+|duration_ms=[0-9]+' | tr '\n' ' '
  printf '\n'
done
