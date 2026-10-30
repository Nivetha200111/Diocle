#!/bin/sh
# Diocle quickstart: certify a small synthetic COBOL sample in one command.
#
#   scripts/quickstart.sh              key mode if a Meta key is configured, else no-key mode
#   scripts/quickstart.sh --no-key     re-verify the checked-in certified conversion; no model call, no key
#   scripts/quickstart.sh --sample NAME   sample under samples/ (default interest-accrual)
#   scripts/quickstart.sh --check      prerequisites, key detection and the cost cap only; changes nothing
#
# Key mode makes REAL model calls to the Meta Model API with YOUR key and costs a few cents.
# The key is read from the environment (META_MODEL_API_KEY) or the repo-root .env, never from an argument, never
# prompted for, never printed. Cost cap: --max-usd 0.10, raise with QUICKSTART_MAX_USD (hard maximum 1.00).
# Tested on macOS. Linux is untested. POSIX sh.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SAMPLE=interest-accrual
MODE=auto
CHECK=0
DEFAULT_CAP=0.10
HARD_CAP=1.00

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }
say() { printf '%s\n' "$*"; }
die() { printf 'quickstart: %s\n' "$*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --no-key) MODE=nokey ;;
    --check) CHECK=1 ;;
    --sample) [ $# -ge 2 ] || die "--sample needs a name"; SAMPLE=$2; shift ;;
    --sample=*) SAMPLE=${1#--sample=} ;;
    *key*|*KEY*|sk-*) die "never pass a key on the command line; put META_MODEL_API_KEY in .env (see .env.example)" ;;
    *) die "unknown argument (not echoed, in case it was a secret; try --help)" ;;
  esac
  shift
done
case "$SAMPLE" in *[!A-Za-z0-9_-]*|"") die "sample name must be letters, digits, - or _" ;; esac
[ -d "$ROOT/samples/$SAMPLE" ] || die "no such sample: samples/$SAMPLE"

# ---- cost cap: QUICKSTART_MAX_USD, clamped to [0.01, 1.00]; anything that is not a number falls back to the default
resolve_cap() {
  raw=${QUICKSTART_MAX_USD:-}
  [ -n "$raw" ] || { echo "$DEFAULT_CAP"; return; }
  case "$raw" in *[!0-9.]*|.|*.*.*) echo "$DEFAULT_CAP"; return ;; esac
  awk -v v="$raw" -v lo=0.01 -v hi="$HARD_CAP" 'BEGIN { if (v+0 < lo) v = lo; if (v+0 > hi) v = hi; printf "%.2f\n", v }'
}
CAP=$(resolve_cap)

# ---- prerequisites
install_hint() {
  case "$(uname -s)" in
    Darwin) say "  macOS:  brew install gnucobol openjdk@21 python@3.12   (then put openjdk@21's bin on PATH, brew prints how)" ;;
    *) say "  Debian/Ubuntu:  sudo apt install gnucobol openjdk-21-jdk python3 python3-venv   (GnuCOBOL must be 3.2 or newer; older apt packages fail this check)" ;;
  esac
}
MISSING=0
need() { MISSING=1; say "MISSING: $1"; }

check_cobc() {
  command -v cobc >/dev/null 2>&1 || { need "cobc (GnuCOBOL 3.2+)"; return; }
  v=$(cobc --version 2>/dev/null | sed -n '1s/.*[^0-9.]\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
  ver_ge "${v:-0.0}" 3 2 || need "GnuCOBOL 3.2 or newer (found ${v:-unknown})"
}
check_java() {
  command -v javac >/dev/null 2>&1 || { need "javac (JDK 21+)"; return; }
  v=$(javac -version 2>&1 | sed -n '1s/^javac \([0-9][0-9]*\).*/\1/p')
  [ "${v:-0}" -ge 21 ] 2>/dev/null || need "JDK 21 or newer (found ${v:-unknown})"
}
ver_ge() { # ver_ge X.Y MAJOR MINOR
  maj=${1%%.*}; min=${1#*.}; min=${min%%.*}
  [ "$maj" -gt "$2" ] 2>/dev/null || { [ "$maj" -eq "$2" ] 2>/dev/null && [ "${min:-0}" -ge "$3" ] 2>/dev/null; }
}
PY=""
find_python() {
  for c in python3 python3.13 python3.12 python3.11; do
    command -v "$c" >/dev/null 2>&1 || continue
    v=$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
    if ver_ge "$v" 3 11; then PY=$c; return; fi
  done
  need "python3 3.11 or newer"
}
check_cobc; check_java; find_python
if [ "$MISSING" -ne 0 ]; then
  say "Install the missing pieces, then run this again:"; install_hint; exit 3
fi

# ---- is a Meta key configured? Looks, never prints. A key counts only if the variable has a non-empty value.
has_key() {
  [ -n "${META_MODEL_API_KEY:-}" ] && return 0
  [ -f "$ROOT/.env" ] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?META_MODEL_API_KEY=[[:space:]]*[^[:space:]#\"']" "$ROOT/.env"
}
if [ "$MODE" = auto ]; then
  if has_key; then MODE=key; else
    MODE=nokey
    say "No Meta key found (META_MODEL_API_KEY in the environment or in $ROOT/.env)."
    say "To run a real conversion with your own key: cp .env.example .env, edit .env, set META_MODEL_API_KEY=..., run this again."
    say "Falling through to no-key mode: no model will be called."
    say ""
  fi
elif [ "$MODE" = nokey ]; then :; fi

if [ "$CHECK" -eq 1 ]; then
  say "check ok: mode=$MODE sample=$SAMPLE cap=$CAP python=$PY"
  exit 0
fi

# ---- one venv for the converter (it installs the verifier too); quiet and idempotent
VENV="$ROOT/services/converter/.venv"
if ! "$VENV/bin/python" -c 'import diocle_converter, diocle_verifier, jsonschema' >/dev/null 2>&1; then
  say "Setting up the Python environment (services/converter/.venv), first run only..."
  "$PY" -m venv "$VENV" >/dev/null
  "$VENV/bin/pip" install -q --disable-pip-version-check -e "$ROOT/services/verifier" -e "$ROOT/services/converter" jsonschema >/dev/null \
    || die "pip install failed; run it without -q in services/converter to see why"
fi
VPY="$VENV/bin/python"
SAMPLE_DIR="$ROOT/samples/$SAMPLE"

if [ "$MODE" = nokey ]; then
  JAVA="$SAMPLE_DIR/certified-java"
  [ -d "$JAVA" ] || die "samples/$SAMPLE has no certified-java directory; no-key mode needs a checked-in certified conversion (try --sample interest-accrual)"
  TMP=$(mktemp -d "${TMPDIR:-/tmp}/diocle-quickstart.XXXXXX"); trap 'rm -rf "$TMP"' EXIT INT TERM
  say "No-key mode: no model is called. GnuCOBOL compiles the original, then the original and the stored Java run on the same inputs."
  start=$(date +%s)
  rc=0
  (cd "$ROOT/services/verifier" && "$VPY" -I -m diocle_verifier "$SAMPLE_DIR" --java-dir "$JAVA" --random 1000 --seed 4243 --out "$TMP/report.json" >"$TMP/out.txt" 2>&1) || rc=$?
  tail -n 3 "$TMP/out.txt"
  "$VPY" -I "$ROOT/scripts/quickstart_report.py" verify "$TMP/report.json" "$SAMPLE" "$JAVA" "$(( $(date +%s) - start ))"
  exit "$rc"
fi

# ---- key mode: one real conversion, capped. The converter reads the key itself (environment or .env).
: "${META_MODEL_BASE_URL:=https://api.meta.ai/v1}"; : "${META_MODEL_ID:=muse-spark-1.3-contributor}"
export META_MODEL_BASE_URL META_MODEL_ID
say "Key mode: this makes REAL model calls with your key, capped at \$$CAP (QUICKSTART_MAX_USD, hard maximum \$$HARD_CAP)."
LOG=$(mktemp "${TMPDIR:-/tmp}/diocle-quickstart.XXXXXX"); trap 'rm -f "$LOG"' EXIT INT TERM
rc=0
(cd "$ROOT/services/converter" && "$VPY" -I -m diocle_converter run "$SAMPLE_DIR" --no-memory --max-usd "$CAP") >"$LOG" 2>&1 || rc=$?
grep -E '^(CERTIFIED|NOT CERTIFIED|CERTIFIED AGAINST)' "$LOG" || tail -n 15 "$LOG"
RUN=$(sed -n 's/^run saved to //p' "$LOG" | tail -n 1)
if [ -n "$RUN" ] && [ -f "$ROOT/$RUN/run.json" ]; then
  "$VPY" -I "$ROOT/scripts/quickstart_report.py" run "$ROOT/$RUN" "$SAMPLE"
else
  say "No run record was written. Last lines of the log ($LOG):"; tail -n 8 "$LOG"
fi
rm -f "$LOG"
exit "$rc"
