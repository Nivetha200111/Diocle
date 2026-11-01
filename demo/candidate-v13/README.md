# Demo candidate v13

The owner chose this over v12 on Nov 1. A separately named cut, `~/Downloads/diocle-candidate-v13.mp4` (169.1 s, 1080p), made only from the v12 picture and the owner's recorded narration. v12 (`~/Downloads/diocle-final-v12.mp4`, currently at https://youtu.be/EsKndaZ6d2E) and the recordings are untouched. No voice was synthesized and no footage invented. The owner uploads it.

Rebuild: `CHROME=<chromium> node overlays.mjs OUT_DIR <dir with playwright>`, then `python3 build.py V12.mp4 OUT_DIR OUT.mp4`. Checked with `demo/final/gates.sh` from the `video-draft-7` branch and at 854x480: the limits card carries the "Open Meta models" line after a 0.8 s beat, and captions sit above the step strip so it stays visible.

## What changed from v12 (v12 timeline)

| Time | v12 | Candidate | Why |
|---|---|---|---|
| 0.0-5.0 | Card: "passed 1,000 tests each" | "about 1,000 generated records" | One run on one file; output records are counted |
| 5.0-9.1 | Card: "broken by the attacker agent"; stamp "WRONG"; banner "Passed 1,004 held-out tests. Still wrong." | "differed under attack"; stamp "DIFFERS"; banner says the record is malformed, under GnuCOBOL, IBM not tested | A malformed-data difference must not read as an ordinary transaction error |
| 32.2-33.9 | Spoken: "Diocle proves it's right." | Cut | Testing, not proof. The next spoken line follows naturally |
| 98.3-112.8 | Three breaks shown, no note; stamp "WRONG" | Caption: letters where numbers belong, malformed, IBM not tested; stamp "DIFFERS" | Same |
| 112.8-119.0 | "passed again on a thousand fresh inputs" | Caption: those records had zero amounts; generator fixed Nov 1; this Java matched 1,000 well-formed records | CHQCLR's check was weak |
| 124.2-129.9 | Spoken: "re-runs the proof" | Caption: the same comparison, pinned verifier, shares its assumptions, not a formal proof | The word stays spoken unless the pickup below is used |
| 146.2-156.5 | Measured panel (old copy on screen: "still wrong") | Caption: by the breaker's stated reasons, 1 malformed + 3 negative zero; different denominators; CHQCLR certified or not | Footage is the earlier page; the caption states the scope |
| 156.6-164.2 | Spoken: "Banks, credit unions and pension payers can leave COBOL with proof instead of faith, for cents a program." | Cut; replaced by a limits card (a 0.8 s beat, no voice) under "Open Meta models can run on a host you choose." | The broadest overclaim in the video |
| 174.0-177.6 | End card | Adds the no-key command, says it re-checks stored Java | A direct invitation that is accurate |

Stored-run, real-time and speed chips are v12's own and stay accurate. Delivery, PR and printout footage is the earlier UI, as in v12.

## Pickups (optional; only the owner's own voice)

Record any of these into QuickTime; each replaces the stated moment. The candidate works without them, but these would remove the remaining spoken looseness.

1. **Goes over the limits card, before "Open Meta models" (strongest improvement).** "This is testing on the inputs tried, under GnuCOBOL. It's not a formal proof, and not IBM's compiler. A person still reviews it and accepts it on their own runtime."
2. **Replaces 0:00-0:09 narration.** "Ten AI translations of COBOL passed a test of a thousand generated records. An attacker model made four of them differ from the original."
3. **Replaces 2:04 "re-runs the proof".** "The new repository's CI re-runs the comparison on fresh inputs. Green."
4. **Replaces the "passed again" line at 1:51.** "The repair agent fixed it, and it matched again on fresh records and a new attack."
5. **Optional, a clearer first beat of the user (after the "checked by hand" line).** "If you're the person who has to accept that Java, this is the check you run first."

Separate from the video: the bundled clip `waiver-tenure.wav` mistranscribes on Muse Voice Transcribe ("It's a free wave for an account with a tenure"). Re-recording "Is the fee waived for an account with a ten-year tenure?" slowly, with the same format (16 kHz mono 16-bit), would fix it; `fee-overdrawn.wav` transcribed exactly.
