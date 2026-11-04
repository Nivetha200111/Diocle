# Before submission

Things only the owner can fill in or confirm. Nothing here is done by the build sessions. Deadline: Nov 4, 2026, 9 PM ET (Nov 5, 7:30 AM IST). Status as of Nov 3, 2026: open boxes below. Draft text to paste: [SUBMISSION_TEXT.md](SUBMISSION_TEXT.md).

- [x] **Final cut uploaded:** https://youtu.be/GgrC0R34QJ4 (2:57, replaces v16; new three-part opening, a sentence on what pre-existed from the first frame, the delivered pull request and its CI as the climax, real pages replacing most slides, captions, ElevenLabs narration, synthesised music and sound effects).
- [x] **YouTube title.** Names Diocle and the Meta Global AI Developer Hackathon.
- [ ] **CI green on the submitted commit**, on GitHub, not only locally (`gh run list --workflow test`).
- [x] **Engine deploy after PR #1.** On `7f87dc2`, Nov 2, with PR #1 ("Nothing to convert") and the clearer no-GitHub-login message; re-check afterwards: 1,004 of 1,004.

- [x] **Demo video link.** https://youtu.be/GgrC0R34QJ4 is in the first line of [README.md](../README.md); it opens without signing in, and it is public (checked Nov 4 through YouTube's public oEmbed endpoint).
- [x] **X post of the final cut (owner reports posted, Nov 4); add its link to the form.** Post the demo on X within the hour after submitting and add the post link to the submission form (Most Viral needs it; Community Vote runs in the public gallery). No vertical cut exists. Post the final cut; X may limit free accounts to 2:20, so link the YouTube video if the upload is refused.
- [ ] **Repository is public** and the default branch shows the latest commit (visibility was `PUBLIC` on Oct 31; recheck at submission).
- [x] **Meta Model API credits claimed (owner, Nov 2)** before Nov 4, 9 PM ET (the claim form is in the official participant guide).
- [ ] **Spend limit set.** Not reported yet.
- [x] **Narration.** The video uses a synthetic voice (ElevenLabs), disclosed in the README and the video description. The owner reports subscribing to the Starter plan on Nov 4, and the narration was regenerated after that.
- [ ] **VS Code F5 check.** Open `editors/vscode` in VS Code, press F5, and confirm the extension host starts and `check` works on a sample. The README says the extension was exercised in a real VS Code extension host for `check` and `convert`; repeat it once before submission if the extension is shown or claimed.
- [x] **Team members.** Solo project (owner, Nov 2); nobody else to list.
- [ ] **License present.** `LICENSE` (MIT) is in the repository root; GitHub shows it as MIT. Recheck the third-party notes in [HACKATHON_COMPLIANCE.md](HACKATHON_COMPLIANCE.md).
- [x] **A sentence on screen from the first frame on what was built and what already existed, the dated line and badge, and "I built Diocle during this hackathon" spoken at about 0:37** (rules: judges must be able to identify what was built in the window).
- [ ] **Counts and dates.** The README states an "as of" date for the live numbers; refresh it if runs are added before submission.
- [ ] **Deploy freeze** after submission (Nov 4, 9 PM ET).
- [ ] **Uptime check that really runs every few minutes.** `.github/workflows/uptime.yml` asks for every 15 minutes, but GitHub has been running it about every 3 to 6 hours. Add an external monitor on `https://diocle.vercel.app/api/health` for judging (Nov 5-9), or accept that gap.
- [ ] **Watch visitor imports** during judging (`GET /api/deliveries`) and the spend limit.
- [ ] **Real microphone on `/try`.** Not yet confirmed by a person.
- [x] **Second-person cold test: dropped (owner, Nov 2).** No one else is available. The only cold test on record is the headless browser one in [LIVE_CHECK.md](LIVE_CHECK.md).
