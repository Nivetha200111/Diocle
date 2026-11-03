# Before submission

Things only the owner can fill in or confirm. Nothing here is done by the build sessions. Deadline: Nov 4, 2026, 9 PM ET (Nov 5, 7:30 AM IST). Status as of Nov 3, 2026: open boxes below. Draft text to paste: [SUBMISSION_TEXT.md](SUBMISSION_TEXT.md).

- [x] **v15 uploaded:** https://youtu.be/8Yz06cdC3yc (full-window re-cut with a live import of AWS CardDemo and the opening line the organizers asked for, replacing v14).
- [x] **YouTube title.** Now "Diocle: AI writes the Java. The running COBOL checks it. | Meta Global AI Developer Hackathon" (read Nov 3 through YouTube's public oEmbed endpoint).
- [ ] **CI green on the submitted commit**, on GitHub, not only locally (`gh run list --workflow test`).
- [x] **Engine deploy after PR #1.** On `7f87dc2`, Nov 2, with PR #1 ("Nothing to convert") and the clearer no-GitHub-login message; re-check afterwards: 1,004 of 1,004.

- [x] **Demo video link.** https://youtu.be/8Yz06cdC3yc is in the first line of [README.md](../README.md); it opens without signing in (checked Nov 3 through YouTube's public oEmbed endpoint).
- [x] **X post (owner reports done, Nov 2); still add its link to the form.** Post the demo on X within the hour after submitting and add the post link to the submission form (Most Viral and Community Vote need it). No vertical cut exists; every cut is landscape, so post v13 or make one first.
- [ ] **Repository is public** and the default branch shows the latest commit (visibility was `PUBLIC` on Oct 31; recheck at submission).
- [x] **Meta Model API credits claimed (owner, Nov 2)** before Nov 4, 9 PM ET (the claim form is in the official participant guide).
- [ ] **Spend limit set.** Not reported yet.
- [x] **Narration.** The submitted video uses only the author's own recorded voice, so no voice-licence check is needed.
- [ ] **VS Code F5 check.** Open `editors/vscode` in VS Code, press F5, and confirm the extension host starts and `check` works on a sample. The README says the extension was exercised in a real VS Code extension host for `check` and `convert`; repeat it once before submission if the extension is shown or claimed.
- [x] **Team members.** Solo project (owner, Nov 2); nobody else to list.
- [ ] **License present.** `LICENSE` (MIT) is in the repository root; GitHub shows it as MIT. Recheck the third-party notes in [HACKATHON_COMPLIANCE.md](HACKATHON_COMPLIANCE.md).
- [x] **(owner checked v13, Nov 2) Video opens with the "built Oct 27 to Nov 4, 2026" card** and shows only what was built in the window (rules: judges must be able to identify it).
- [ ] **Counts and dates.** The README states an "as of" date for the live numbers; refresh it if runs are added before submission.
- [ ] **Deploy freeze** after submission (Nov 4, 9 PM ET).
- [ ] **Uptime check that really runs every few minutes.** `.github/workflows/uptime.yml` asks for every 15 minutes, but GitHub has been running it about every 3 to 6 hours. Add an external monitor on `https://diocle.vercel.app/api/health` for judging (Nov 5-9), or accept that gap.
- [ ] **Watch visitor imports** during judging (`GET /api/deliveries`) and the spend limit.
- [ ] **Real microphone on `/try`.** Not yet confirmed by a person.
- [x] **Second-person cold test: dropped (owner, Nov 2).** No one else is available. The only cold test on record is the headless browser one in [LIVE_CHECK.md](LIVE_CHECK.md).
