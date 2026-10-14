# Model B: band combination changes conditional satellite assignments

The original B winners were replayed on the two worst cases (039, 023) and
two best controls (005, 003). For each half, the diagnostic aligns its exact
observation window identities to the all-band observations, verifies the same
ordered satellite bank, and compares posterior probabilities including clutter.
All twelve original objective values replayed exactly. There were twelve
objective evaluations, zero fits, no held preparation and no reference lookup.

| Original case | Historical all error km | MAP assignment changed | Mean total variation | Conflicting assignments among mutually confident windows |
|---|---:|---:|---:|---:|
| 039, worst | 8.599847 | 42.85% | 0.42249 | 35.54% |
| 023, second worst | 5.599817 | 41.02% | 0.41320 | 34.07% |
| 005, best | 1.271893 | 33.90% | 0.32751 | 28.50% |
| 003, second best | 2.346276 | 20.77% | 0.21348 | 16.06% |

MAP means the highest probability satellite or clutter category. Mutually
confident means both distributions assign at least 0.9 to their own winning
category. Total variation is half the sum of absolute probability differences;
zero means identical distributions and one means disjoint probability mass.
The table pools disjoint low/high windows by observation count. These are
conditional model probabilities, not confirmed satellite identities.

| Case | Low mean total variation | High mean total variation | Low satellite switches when both favor signal | High satellite switches when both favor signal |
|---|---:|---:|---:|---:|
| 039 | 0.46205 | 0.36197 | 376 / 966 | 139 / 572 |
| 023 | 0.49854 | 0.30788 | 395 / 783 | 91 / 626 |
| 005 | 0.21748 | 0.46677 | 94 / 722 | 118 / 396 |
| 003 | 0.29405 | 0.10495 | 201 / 964 | 53 / 884 |

The worst pair has more aggregate disagreement than the best pair. However,
005 has the largest high-band disagreement despite being the best original
all-band position result; 003 and 005 also reverse their error ranking under
this measure. Association instability is therefore a discriminating hypothesis,
not a monotonic accuracy predictor or a demonstrated causal explanation.
In particular, each distribution uses its own training-selected geography,
calibration and timing. The diagnostic cannot separate a changed geographic
mode from calibration bias or association ambiguity.

A useful next controlled intervention is to fix geography in turn to each
training-selected all/low/high solution, profile nuisance parameters under the
same all-band observations and candidate bank, and compare the resulting
assignments. Its hypothesis, starts and budget must be specified before fitting;
held frequency scoring and reference error evaluation must follow sealed
training outcomes, with neither used to select a recording-specific winner.

The four audits completed in 17.222, 13.265, 10.915 and 13.798 seconds for
039, 023, 005 and 003 respectively. Each retained 180/195/200-second
internal/TERM/KILL bounds. Pre-preparation authority reused the original
worst-case or best-control freeze and additionally bound and archived both new
diagnostic sources. Original source, input and receipt bindings were rechecked
afterward. Raw results are in `local/model-b-assignments-{039,023,005,003}`.

Seven component tests passed, covering reordered window identities, clutter,
confident contradictory assignments, invalid probability distributions, missing
windows and mismatched candidate dimensions. Ruff passed for both sources and
the tests. No frozen scientific implementation, contract or fixture changed.
As elsewhere, the original half fits share discovery and proposals; these are
not independent end-to-end band-only runs.
