#!/bin/sh
# Install the Diocle plugin into Muse Code (a local plugin: MCP server + skill + slash commands).
#
#   sh editors/muse-code/install.sh              stage a copy and install it (user scope), then show the next step
#   sh editors/muse-code/install.sh --dry-run    print what would change, change nothing
#   sh editors/muse-code/install.sh --allow-convert   also enable diocle_convert (REAL model spend; see README)
#   sh editors/muse-code/install.sh --uninstall  remove the plugin (and the allow-convert marker)
#
# What it changes (and nothing else):
#   1. writes a staged copy of editors/muse-code/plugin to $XDG_DATA_HOME/diocle-muse/plugin (default ~/.local/share/...),
#      plus mcp/repo.txt holding the absolute path of this Diocle checkout;
#   2. runs `muse plugins install` (or `update` if already installed) on that copy: a user-level Muse Code plugin;
#   3. with --allow-convert only: creates $XDG_CONFIG_HOME/diocle-muse/allow-convert (an empty file).
# Muse Code asks you to review the plugin's MCP server before it runs; this script never approves it for you.
# Idempotent. No key is read, written or printed. Not an official Meta integration. POSIX sh.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd -P)
MUSE=${MUSE:-muse}
DATA=${XDG_DATA_HOME:-$HOME/.local/share}/diocle-muse
CONF=${XDG_CONFIG_HOME:-$HOME/.config}/diocle-muse
DRY=0; ALLOW=0; UNINSTALL=0
say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 2; }

for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --allow-convert) ALLOW=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument (try --help)" ;;
  esac
done
command -v "$MUSE" >/dev/null 2>&1 || die "Muse Code ('$MUSE') not found on PATH"
command -v python3 >/dev/null 2>&1 || die "python3 not found (the MCP server uses only the standard library)"

act() { if [ "$DRY" -eq 1 ]; then say "would run: $*"; else "$@"; fi; }

if [ "$UNINSTALL" -eq 1 ]; then
  say "Removing the Diocle plugin from Muse Code and the staged copy."
  act "$MUSE" plugins remove diocle || say "(plugin was not installed)"
  if [ "$DRY" -eq 1 ]; then say "would remove: $DATA and $CONF/allow-convert"; else rm -rf "$DATA"; rm -f "$CONF/allow-convert"; fi
  exit 0
fi

[ -f "$HERE/plugin/.muse-plugin/plugin.json" ] || die "plugin sources missing under $HERE/plugin"
say "Diocle checkout: $REPO"
say "Staging the plugin at: $DATA/plugin"
if [ "$DRY" -eq 0 ]; then
  rm -rf "$DATA/plugin"; mkdir -p "$DATA"
  cp -R "$HERE/plugin" "$DATA/plugin"
  find "$DATA/plugin" -name __pycache__ -type d -prune -exec rm -rf {} +
  printf '%s\n' "$REPO" > "$DATA/plugin/mcp/repo.txt"
  "$MUSE" plugins validate "$DATA/plugin" --json >/dev/null || die "Muse Code rejected the plugin; run: $MUSE plugins validate $DATA/plugin"
else
  say "would copy $HERE/plugin and write mcp/repo.txt with the checkout path; then validate it"
fi

if "$MUSE" plugins list --json 2>/dev/null | grep -q '"id": *"diocle"'; then
  say "Already installed: refreshing it."
  act "$MUSE" plugins update diocle
else
  act "$MUSE" plugins install "$DATA/plugin"
fi

if [ "$ALLOW" -eq 1 ]; then
  say "Enabling diocle_convert (REAL Meta model spend, capped at USD 0.10 per call by default, hard maximum 0.25)."
  if [ "$DRY" -eq 1 ]; then say "would create: $CONF/allow-convert"; else mkdir -p "$CONF"; : > "$CONF/allow-convert"; fi
else
  say "diocle_convert stays disabled (re-run with --allow-convert to enable it; it spends money on your Meta key)."
fi

cat <<MSG

Next: Muse Code reviews a third-party plugin's MCP server before it runs. Inspect and approve it yourself:
  $MUSE plugins inspect diocle
  $MUSE plugins approve diocle
Then start Muse Code in any project and try:  /diocle-analyze samples/interest-accrual
Requirements for the verify tools: GnuCOBOL 3.2 (cobc), JDK 21, and a Diocle Python venv (see editors/muse-code/README.md).
MSG
