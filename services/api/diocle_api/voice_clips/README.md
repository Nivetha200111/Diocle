# Bundled voice clips

Two short clips for the public "Ask the original program" panel. Both are a **synthetic voice made with macOS `say`**
(`say -o X.wav --data-format=LEI16@16000 "..."`), 16 kHz mono 16-bit PCM WAV, no recording of any person.

| file | sample it asks about | spoken question |
| --- | --- | --- |
| `fee-overdrawn.wav` | `interest-accrual` | What happens to the fee when the account is overdrawn? |
| `waiver-tenure.wav` | `loyalty-waiver` | Is the fee waived for an account with a ten-year tenure? |

The public path accepts only these two names. They are served by `GET /asks/clips/{name}` so the visitor can hear them.
