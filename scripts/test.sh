#!/bin/sh
# One command to install and test everything:  sh scripts/test.sh [--fast] [--web] [--no-install]
#   (default)     all suites: analyzer, verifier, converter, api. Needs GnuCOBOL 3.2 (cobc), a JDK 21 (javac) and curl.
#   --fast        deselect tests marked `toolchain` (they run real cobc/javac/the SQLite JDBC jar); no cobc/javac needed.
#   --web         also type-check apps/web (npm ci if node_modules is missing, then tsc --noEmit).
#   --no-install  reuse the venv as is.
# One venv at <repo>/.venv (gitignored) with the four packages installed editable, so verifier -> analyzer and
# converter -> verifier -> analyzer imports resolve exactly as in deploy/Dockerfile.api. Fetches the pinned SQLite JDBC
# jar (scripts/fetch-sqlite-jdbc.sh). Every suite runs even if an earlier one fails; exit status is non-zero if any
# failed, errored, or collected nothing. The `toolchain` marker is registered in each service's pyproject.toml and
# applied in services/*/tests/conftest.py.
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
fast=0; web=0; install=1
for a in "$@"; do
  case "$a" in
    --fast) fast=1 ;; --web) web=1 ;; --no-install) install=0 ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

PY=${PYTHON:-python3}
venv="$root/.venv"
if [ "$install" = 1 ]; then
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11+ is required (found: $("$PY" --version 2>&1)); set PYTHON=/path/to/python3.12" >&2; exit 1; }
  [ -x "$venv/bin/python" ] || "$PY" -m venv "$venv" || exit 1
  echo "== installing the four packages (editable) into $venv"
  "$venv/bin/pip" install -q --disable-pip-version-check \
    -e "$root/services/analyzer" -e "$root/services/verifier" -e "$root/services/converter" -e "$root/services/api" \
    pytest httpx jsonschema || { echo "pip install failed" >&2; exit 1; }
fi
[ -x "$venv/bin/python" ] || { echo "no venv at $venv; run without --no-install" >&2; exit 1; }

marker=""
if [ "$fast" = 0 ]; then
  for t in cobc javac java; do
    command -v "$t" >/dev/null 2>&1 || { echo "missing $t: the full run needs GnuCOBOL 3.2 and a JDK 21 (use --fast to skip toolchain tests)" >&2; exit 1; }
  done
  sh "$root/scripts/fetch-sqlite-jdbc.sh" || exit 1
else
  marker="not toolchain"
fi

fail=0
summary=""
for s in analyzer verifier converter api; do
  echo "== $s"
  out=$(cd "$root/services/$s" && "$venv/bin/python" -m pytest -q -rfE ${marker:+-m "$marker"} 2>&1)
  rc=$?
  printf '%s\n' "$out" | tail -25
  line=$(printf '%s\n' "$out" | tail -1)
  summary="$summary
$s: $line"
  # exit 5 = nothing collected: treat as failure, a suite that runs nothing proves nothing.
  [ "$rc" -eq 0 ] || fail=1
done

if [ "$web" = 1 ]; then
  echo "== web (tsc --noEmit)"
  ( cd "$root/apps/web" && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npx --no-install tsc --noEmit )
  rc=$?; [ "$rc" -eq 0 ] && summary="$summary
web: tsc ok" || { summary="$summary
web: tsc FAILED"; fail=1; }
fi

echo; echo "== summary$summary"
if [ "$fail" -ne 0 ]; then echo "RESULT: FAILED" >&2; exit 1; fi
echo "RESULT: ok"
