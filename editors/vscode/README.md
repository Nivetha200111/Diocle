# Diocle for VS Code

Check that a COBOL file compiles under GnuCOBOL, then convert it to Java and verify it, from the editor. Works in VS Code and forks (Cursor, VSCodium, Windsurf). It runs the Diocle converter on your machine, with your own Meta key.

## Install

You need Python with `diocle_converter` installed (this repository: `services/converter`), GnuCOBOL 3.2 (`cobc`) and a JDK 21 on `PATH`.

```
cd editors/vscode
npm install
npm run package                      # writes diocle-0.1.0.vsix
code --install-extension diocle-0.1.0.vsix     # or: cursor / codium / windsurf --install-extension ...
```

Open the Diocle repository (or any folder where `services/converter/.venv` exists) as the workspace, or set `diocle.converterPython`.

## Commands (Command Palette, editor and Explorer context menu on `.cbl .cob .cobol .cpy`)

- **Diocle: Check that this COBOL compiles** - `cobc -x -std=ibm` with your copybook folders; errors appear in the Problems panel at the reported file and line. Cleared on the next check.
- **Diocle: Convert and verify this COBOL file** - confirms the cost first, shows progress (cancellable), then a result page.
- **Diocle: Open the last result**, **Diocle: Show cost and settings**.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `diocle.converterPython` | empty (user/machine setting only; a workspace cannot choose the program to run) | Python with the converter. Empty: `services/converter/.venv` in the workspace, else `python3`. |
| `diocle.maxUsd` | 0.25 | Hard dollar cap per conversion (maximum 1.00). |
| `diocle.convertAnyway` | false | Also try files Diocle would refuse, and repair a file that does not compile. |
| `diocle.copybookPaths` | [] | Folders searched for COPY members. The file's own folder is always searched. |
| `diocle.confirmCost` | true | Ask before each conversion. |

## The Meta key

The key is **not** an editor setting and the extension never reads it. The converter reads it from your environment or from a `.env` file in the workspace folder (names: see `.env.example` in the repository). Keep `.env` out of git.

## What the badges mean

- **CERTIFIED**: the Java matched the original COBOL byte for byte on the inputs tried. Not a proof.
- **CERTIFIED AGAINST REPAIRED COBOL**: your original did not compile. A model patched N lines (the diff is shown) and the Java matched the *patched* COBOL. A person must confirm the patch. Not plain certified. Your file is never overwritten; the patched copy is written to the run folder.
- **COMPILED, NOT VERIFIED**: the Java compiles but was never run against the original. The reason is shown.
- **FAILED**, **SKIPPED**: nothing proven / nothing converted.

## Privacy

The extension itself makes no network calls and has no telemetry. A conversion sends your COBOL and copybooks to the Meta Model API with your own key (through the converter). Nothing goes to Diocle servers. Results are written under `.diocle/runs/` in the workspace; add `.diocle/` to `.gitignore`. A conversion spends your own money, capped by `diocle.maxUsd`; cancelling stops the process but calls already made are billed.

## Safety

The workspace must be trusted (`untrustedWorkspaces: false`): verification compiles and runs workspace code. Processes are started with argument arrays (no shell). The result page has a strict CSP, no remote resources, and escapes all model-written text.

## Develop and test

`npm test` compiles and runs the headless tests (`node:test`, with a stub of the `vscode` module). To try it in a window: open `editors/vscode` in VS Code and press F5.

## Publishing (owner only)

Not published. Needs a publisher account: create a publisher at the Visual Studio Marketplace, a personal access token with Marketplace manage scope, set `"publisher"` in `package.json`, then `npx vsce publish`. For Open VSX (VSCodium, Cursor): `npx ovsx publish diocle-*.vsix -p <token>`.
