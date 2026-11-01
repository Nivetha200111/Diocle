# Bundled voice clips

Two short clips for the public "Ask the original program" panel. Both are the **author's own recorded voice** (recorded Nov 1, 2026;
replacing earlier macOS `say` clips), 16 kHz mono 16-bit PCM WAV, trimmed and level-normalised with ffmpeg.

| file | sample it asks about | spoken question |
| --- | --- | --- |
| `fee-overdrawn.wav` | `interest-accrual` | What happens to the fee when the account is overdrawn? |
| `waiver-tenure.wav` | `loyalty-waiver` | Is the fee waived for an account with a ten-year tenure? |

The public path accepts only these two names. They are served by `GET /asks/clips/{name}` so the visitor can hear them.
