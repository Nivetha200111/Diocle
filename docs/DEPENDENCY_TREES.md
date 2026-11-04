# Dependency trees, drawn by Muse Image and checked

**What it is.** The analyzer finds a repository's dependencies from the source, with no model: `CALL`, `COPY` and JCL links. Muse Image (`muse-image-1.0`) draws them. Muse Wonder (`muse-wonder-1.0`) then reads the picture without seeing the graph, and code compares what it read with the analyzer's links. A drawing shows as verified only on an exact match of boxes and arrows, ignoring case and surrounding spaces.

**The analyzer's links are the source of truth,** and the site draws its own exact tree from them next to any drawing. The site's impact view also uses only those links, in the browser, with no model.

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
