# Diocle for Notepad++

Check that a COBOL file compiles under GnuCOBOL, and convert it to Java and verify it, from Notepad++. This is a script around the same converter command line the VS Code extension uses (`python -m diocle_converter editor check|convert FILE`, JSON contract `contracts/editor-result.schema.json`). Notepad++ has no marketplace-style extension API like VS Code, so there is nothing to publish: you copy files and add a menu entry.

## Not tested in Notepad++

Notepad++ is Windows-only; this was built on macOS. **No line of this has run inside Notepad++.** What was verified, on macOS:

- the pure logic (`diocle_labels.py`, `diocle_summarize.py`) with pytest: label wording identical to the VS Code extension (`editors/vscode/src/core.ts`, compared by the test), result validation, argument builder (paths with spaces and quotes), diagnostic-to-line mapping, console sanitising of hostile text;
- `diocle_npp.py` with a **stub** of the `Npp` module (the flow: dirty-file prompt, annotations on the reported line, cost prompt, Java opened in a tab, label box). The stub is my reading of the PythonScript API, not the real plugin;
- the real converter CLI: `editor check` on `samples/convert-anyway-repo/cobol/NOPERIOD.cbl` (line 5 reported) piped through `diocle_summarize.py`, and `--run` mode.

**Not verified:** every real Notepad++ and PythonScript call (`notepad.*`, `editor.annotation*`, indicators, `console.write`), PythonScript menu/shortcut setup, NppExec syntax and its console filter, Windows paths and `CREATE_NO_WINDOW`, a real `editor convert` through this script (the VS Code extension's real convert is the evidence for the CLI itself; no paid convert was run for this script). Expect to fix small things on first use and please report them.

## Option A: PythonScript plugin (`diocle_npp.py`)

Requires **PythonScript 3** (Python 3.x; the older PythonScript 2 with Python 2.7 is not supported: the code uses Python 3 only).

1. Plugins > Plugins Admin > install **Python Script**, restart Notepad++.
2. Copy `diocle_npp.py` and `diocle_labels.py` into the same folder under `%APPDATA%\Notepad++\plugins\config\PythonScript\scripts\` (user scripts folder).
3. Plugins > Python Script > Configuration: add `diocle_npp` ... or create two tiny scripts there, `Diocle check.py` containing `import diocle_npp; diocle_npp.diocle_check()` and `Diocle convert.py` with `diocle_npp.diocle_convert()`. Add them to the menu (Configuration, "Menu items") and bind shortcuts in Settings > Shortcut Mapper > Plugin commands.
4. Settings are constants at the top of `diocle_npp.py`: `CONVERTER_PYTHON` (a Python that has the converter installed, for example the repo's `services\converter\.venv\Scripts\python.exe`; or env `DIOCLE_NPP_PYTHON`), `MAX_USD` (default 0.25; env `DIOCLE_NPP_MAX_USD`), `CONVERT_ANYWAY` (default False), `COPYBOOK_DIRS`.
5. GnuCOBOL (`cobc`) must be on PATH for `check`.

**Check** saves the file first (it asks if there are unsaved changes), runs `editor check`, prints `file:line: severity: message` in the PythonScript console and marks the reported lines with a squiggle and an annotation under the line. Diagnostics in copybooks are listed in the console only.

**Convert** shows a cost message ("at most $0.25, hard cap $1.00", and that code goes to the Meta endpoint), then runs `editor convert` with the converter's progress lines in the console, opens the generated Java in a new tab and shows the label in a message box. The Notepad++ UI is busy until the command ends (the script is synchronous). Labels, same words as VS Code:

- `CERTIFIED`: the generated Java matched the original COBOL byte for byte on the inputs tried; not a proof.
- `CERTIFIED AGAINST REPAIRED COBOL`: your COBOL did not compile; a model patched N lines and the Java matched the patched COBOL; a person must confirm the patch.
- `COMPILED, NOT VERIFIED`: the Java compiles but was never run against the original COBOL.
- `FAILED` / `SKIPPED`: with the reason.

## Option B: NppExec (`diocle_check.npp.txt`, `diocle_convert.npp.txt`)

1. Install the **NppExec** plugin (Plugins Admin).
2. Plugins > NppExec > Execute..., paste a script, edit `DIOCLE_DIR` and `DIOCLE_PY`, save it under a name, and optionally add it to the menu (Advanced Options).
3. The scripts save the file (`NPP_SAVE`), `cd` to its folder and run `diocle_summarize.py --run check|convert $(FULL_CURRENT_PATH)`, which starts the converter with an argument list and prints the JSON line, the PROGRESS lines and a short summary. `diocle_summarize.py` also reads an editor-result JSON on stdin (`python diocle_summarize.py check < result.json`) for use anywhere else.
4. Clickable errors: the summary prints `file:line: error: message`. In the NppExec console use Console > "Highlight Filters" (HighLight masks) with a mask such as `%FILE%:%LINE%: error:` so a double click jumps to the line. I recalled that syntax from the NppExec docs and have not tried it.

## The Meta key and privacy

The key is not a setting here and these scripts never read it. The converter reads it from your environment or from a `.env` file in the workspace folder (the nearest parent of the file that has `.env` or `.git`, else the file's folder). Names: see `.env.example` in the repository. Keep `.env` out of git.

A conversion sends your COBOL and the copybooks it COPYs to the Meta model endpoint set in your `.env`, with your own key. Nothing goes to Diocle servers, no telemetry. Results are written under `.diocle\runs\` in the workspace; add `.diocle/` to `.gitignore`. Cancelling is not offered; calls already made are billed.

## Safety

The converter is started with an argument list, never a shell string (the NppExec scripts use the helper for the same reason). Paths with spaces and quotes are passed as one argument. The spend cap is `--max-usd` (default 0.25), clamped to 1.00 here and enforced again by the converter. `convert anyway` is off unless you set the constant. Verification compiles and runs the COBOL and the generated Java on your machine: only use it on code you trust, as with any build. All text from the compiler or the model is stripped of control characters before it reaches the console or a message box.

## Tests

`pytest editors/notepadpp/tests` (standard library only; the real-CLI test runs when a converter Python is found at `services/converter/.venv` or `DIOCLE_TEST_CONVERTER_PYTHON`, and `cobc` is installed).

## Untrusted folders
The converter runs as `python -m diocle_converter` from the workspace folder, so do not use it on a folder you do not trust (a hostile folder could contain its own `diocle_converter` package that Python would import first).
