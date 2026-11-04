# Dependency trees, drawn by Muse Image and checked

**What it is.** The analyzer finds a repository's dependencies from the source, with no model: `CALL`, `COPY` and JCL links. Muse Image (`muse-image-1.0`) draws them. Muse Wonder (`muse-wonder-1.0`) then reads the picture without seeing the graph, and code compares what it read with the analyzer's links. A drawing shows as verified only on an exact match of boxes and arrows, ignoring case and surrounding spaces.

**The analyzer's links are the source of truth,** and the site draws its own exact tree from them next to any drawing. The site's impact view also uses only those links, in the browser, with no model.

## Every import gets its own tree

Each new delivery, visitor imports included, records the analyzer's links in `dependencyTree` ([`contracts/delivery.schema.json`](../contracts/delivery.schema.json) v0.9) as soon as analysis finishes, before any conversion, even when nothing in the repository can be converted. No model is involved.

- **What is recorded:** kinds `call`, `copy` and `job`, as analyzed; each distinct link once, in analyzer order. The analyzer's `file` links are not part of the tree.
- **Limits:** the first 1,000 distinct links, with `total` and `truncated` saying so, and the page says so too. Labels are cut at 120 characters, and control and text-direction characters become `?`.
- **On the page:** the delivery page shows the repository and commit and one collapsed group per program or JCL job. A group's tree is built only when it is opened, so a repository with hundreds of links stays quick (the check script times 1,000 links). Labels come from the imported repository and are rendered as text only.
- **Impact covers only the links in the report.** It does not cover everything that could break at run time. A delivery from before this field shows one line saying no tree is recorded.

## An optional drawing of one small part of an import

A delivery can also get one Muse Image drawing, by the same check as the results below. It is off unless the engine sets `TREE_IMAGE_MODEL_ID`; with that empty, nothing is called or written and the page shows one neutral line. It runs as its own job after the analyzer's tree is recorded (`services/converter/diocle_converter/treedraw.py`, record `dependencyDrawing` in the contract, v0.10). A failed or capped drawing never fails or delays a delivery.

- **What is drawn:** the first program or job in analyzer order with 2 to 8 links of its own, those links only, never a whole repository. A link from a name to itself is not drawn. A part with a label outside `^[A-Z0-9#@$-]{1,30}( [A-Z0-9#@$-]{1,30})?$` after upper-casing is skipped and the next one is considered, so a repository's text cannot reach the image prompt as instructions.
- **The read-back** gets the picture and a fixed prompt, never the graph. Its reply is parsed as data only and goes through the exact comparison.
- **Caps, each checked before the call it limits, failing closed:**

| Cap | Limit | Enforced by |
|---|---|---|
| Attempts per delivery | 2 | The job, and the image ledger on disk |
| Images a day, all visitors together | 6, over a rolling 24 hours | The image ledger on disk, written before each call, so a failed call still counts. An unreadable ledger means no call |
| Drawing jobs per visitor a day | 1 | The API, in memory, by address, like the other per-visitor limits: best effort, and an engine restart resets it. The ledger is the hard limit |
| At one time | 1 | A file lock; a second job records `busy` and draws nothing |
| Read-back spend per delivery | $0.15 | The job, at the Muse Wonder list price; the worst case of a read (4,000 input and 3,500 output tokens, the output capped in the request) must fit before an image is drawn. A read with no usage, or one lost to a dropped connection, is charged that worst case |

The caps are constants in the code, not settings. Muse Image's price is not published, so it is not given one: images are counted, and the token usage it returns is recorded. This spend is separate from the public budget for imports (`DIOCLE_PUBLIC_DAILY_USD`): it does not draw from it and is not stopped by it, so **Muse Image's cost is limited only by the image count.**

- **What is kept:** only a drawing that passed, at most 4 MB, in the delivery's own directory under a fixed name, served by `GET /deliveries/{id}/dependency-drawing`. A drawing that did not pass is not kept, so it cannot be looked at afterwards. Its counts stay in the record.
- **On the page:** a pass says so and names the attempt. A drawing that did not pass shows one line, and so does a delivery with no drawing. A rejection can be wrong, as below, and a pass is not a proof.
- **One real run through this job** (Nov 4, not on the live engine): the 3 links of `BANK-MAIN` from `fzn0x/core-banking-system`, 1 image, passed on attempt 1, read-back about $0.03. One run shows it works; it says nothing about how often it passes.

## Results

Raw records: [`results-dependency-trees.json`](../eval/results-dependency-trees.json), whole graphs, up to 2 attempts each; [`results-dependency-trees-parts.json`](../eval/results-dependency-trees-parts.json), one program at a time, up to 3 attempts each. The generator is `eval/draw_dependency_trees.py`. Every attempt is recorded.

| Graph | Links | Result |
|---|---:|---|
| `navikt/DSF`, CALL links | 3 | Passed on attempt 2 |
| `fzn0x/core-banking-system`, CALL links | 4 | Passed on attempt 2 |
| Quillmark, whole repository (synthetic) | 20 | **Did not pass**, 2 attempts |
| Harbor Trust, whole repository CALL links (synthetic) | 34 | **Did not pass**, 2 attempts |
| 6 Quillmark programs, one at a time: job, program, copybooks (synthetic) | 3 to 5 each | Each passed on attempt 1 |
| 2 Harbor Trust programs, one at a time: CALLs (synthetic) | 3 each | Each passed on attempt 1 |

So small trees passed, and whole-repository drawings did not, in this one run of 16 images. Large repositories are shown from the analyzer's tree, and only small parts have verified drawings.

## How to read the check

- **It can reject a good drawing.** The first `navikt/DSF` drawing looks correct on inspection, but Muse Wonder read `FO04F1X1` as `F004F1X1`, so it was rejected. A rejection does not by itself show which model was wrong.
- **It can catch a bad one.** The first whole-Quillmark drawing chains copybooks together, such as `CHGREC` to `FEEREC`, which the analyzer does not report.
- **It is not a proof.** A wrong drawing passes only if Muse Wonder misreads it into exactly the analyzer's graph, and that is not impossible. Trust the analyzer's tree over a drawing.
- **The analyzer has limits too.** It reads the source it is given. A dynamic CALL or a refused program may leave links out, so the impact view says which programs depend on something in the analyzer's report, not everything that could break at run time.
- **Samples:** four repositories, two of them synthetic estates, and every verified tree has 5 links or fewer. The DSF graph has only 3 links, and whether those programs ran in production is not established.

**Cost.** Reading back cost about $1.12 at list prices. Muse Image's price is not published, so its 16 images are not priced here. Their token counts are in the records.
