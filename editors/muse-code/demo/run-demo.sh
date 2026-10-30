#!/bin/sh
# Record the real Muse Code demo runs for the video. RUN THIS YOURSELF: it uses YOUR Muse login (`muse login`) or META_API_KEY,
# which this script never reads, and run 3 spends real Meta model money (about USD 0.02 to 0.05 for the conversion, plus the
# agent's own tokens). Five headless runs in total; each is capped by --max-model-steps.
#
#   sh editors/muse-code/install.sh --allow-convert && muse plugins approve diocle     (once)
#   sh editors/muse-code/demo/run-demo.sh [1 2 3 4 5]       (default: all five)
#   python3 editors/muse-code/demo/render_capture.py OUT.mp4 --max-seconds 40 editors/muse-code/transcripts/run-*.jsonl
#
# 1 analyze + verify (free)   2 live run lookup (free)   3 convert + certify (REAL SPEND, needs install.sh --allow-convert)
# 4 guardrail: path escape    5 guardrail: convert refused (run it with the marker removed: rm ~/.config/diocle-muse/allow-convert,
#   e.g. `sh demo/run-demo.sh 5` before enabling convert, or after removing the marker again).
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$HERE/../transcripts"; mkdir -p "$OUT"
MUSE=${MUSE:-muse}
PROJ=$(mktemp -d "${TMPDIR:-/tmp}/diocle-muse-demo.XXXXXX")   # a scratch project; the Diocle checkout is not the workspace
WANT=${*:-1 2 3 4 5}
run() { # N title prompt
  n=$1; title=$2; prompt=$3
  case " $WANT " in *" $n "*) ;; *) return 0 ;; esac
  (cd "$PROJ" && python3 "$HERE/timed_run.py" "$OUT/run-$n.jsonl" --title "$title" -- \
     "$MUSE" exec --json --disable-approval --disable-shell --disable-write --disable-web-tools --max-model-steps 12 --reasoning-effort low "$prompt")
}
run 1 "Muse Code + Diocle: analyze and re-verify (free, no model spend by Diocle)" \
  "Use the diocle tools: analyze samples/interest-accrual, then verify its stored Java. Report the counts and the honest caveat in 5 lines."
run 2 "Muse Code + Diocle: read a live run (read-only)" \
  "Use diocle_live_run to read run chqclr-20261028-214355 and explain it in 4 lines, with the honest caveat."
run 3 "Muse Code + Diocle: convert and certify (REAL model spend, capped)" \
  "I agree to spend up to USD 0.10. Use the diocle tools to convert samples/interest-accrual with Muse Spark and certify it. Report CERTIFIED or not, the counts, the cost, and the honest caveat."
run 4 "Guardrail: a path outside the repo is refused" \
  "Use diocle_analyze on /etc and then on ../../../etc. Report exactly what the tool said."
run 5 "Guardrail: convert is refused unless the owner enabled it" \
  "I agree to spend up to USD 0.10. Use diocle_convert on samples/interest-accrual. Report exactly what the tool said."
echo "transcripts: $OUT (review them for anything private before committing)"; rm -rf "$PROJ"
