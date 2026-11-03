# DS8 N40 timing reselection: a local ambiguity, not an accuracy improvement

One scan explains essentially all of the training improvement available through the declared timing reselection at the previously selected N40 endpoint. Its timing shifts by **−0.397058 s**, with seven conditional-signal top-candidate changes. A subsequent qualified joint fit improves training and held prediction but moves from **416.763 m to 424.581 m** from the supplied reference. The second refit fails the unchanged optimizer-success requirement, so this experiment does not establish endpoint convergence.

## Fixed-position diagnosis

At each original N40 endpoint, each scan receives three timing starts: its own timing, the other endpoint timing, and the best point on the unchanged 41-point training timing grid. Highest qualified training score selects the timing. No held observations or reference distance enter selection. The original aggregate training and held scores replay to within 1e−7.

| Fixed endpoint | Qualified scan selections | Training gain | Held gain | Largest timing change | Top-candidate changes |
|---|---:|---:|---:|---:|---:|
| Original-start N40 | 40/40 | +5.208376 | +25.924366 | 0.397058 s | 7 |
| Rank-start N40 | 40/40 | <0.00000001 | −0.000123 | 0.00000244 s | 0 |

The material change occurs in `scan-fw-2397fe2b6f23337a`: training gain +5.208376334, held gain +25.924134810, and all seven candidate changes. Other changes are numerical-scale refinements. Conditional-signal top-candidate changes do not prove true satellite identity.

Of 240 attempted timing fits, 226 qualify. Fourteen return `ABNORMAL` optimizer status and are excluded even though their gradient norms are small. Every scan/location pair has at least one qualified attempt. All attempts, including failures, are retained in [results.json](results.json). The complete fixed-position run took 62.51 seconds, within its 180-second cap.

## Joint refits

The [follow-up protocol](REFIT_PROTOCOL.md) was written after the diagnosis and before either joint refit. Both use the same likelihood and constraints, initialized with their training-selected timings. There are no retries or relaxed qualification checks.

| Start | Qualification | Training gain vs its original N40 fit | Held gain | Position shift | Reference distance |
|---|---|---:|---:|---:|---:|
| Original-start, reselected timings | Pass | +5.479824 | +25.573030 | 33.500 m | 424.581 m |
| Rank-start, reselected timings | Fail: optimizer `ABNORMAL` | — | — | — | — |

The qualified fit has projected gradient 0.001792, gradient-audit discrepancy 0.00001904, and no boundary hit. The failed fit has projected gradient 0.0002644, audit discrepancy 0.00001962 and no boundary hit, but remains unqualified because optimizer success is required. Its training score differs from its original endpoint by less than 1e−8. This is not a timeout: both processes exited normally after approximately 38 seconds and preserved their optimizer outcomes.

## Interpretation and next decision

Per-scan timing optimization has local alternatives that a joint fit can retain. Revisiting them using training data improves this likelihood. It does **not** improve reference distance here, and cannot explain away all of the prior 273 m endpoint disagreement. The failed second refit prevents a qualified two-endpoint convergence comparison.

The next discriminating experiment should profile multiple local timing maxima, rather than retaining only the best coarse-grid seed, on the few scans with substantially different endpoint timings. Any broader algorithm must then be evaluated at a fixed scan budget on other recording groups. No production change is warranted from this DS8 diagnostic alone.

This uses the same exposed forty scans, site-conditioned candidate banks and zero-height model as the [N40 experiment](../2026_09_29_ds8_union40/README.md). Held observations are within the same recordings. Reference uncertainty remains unsupplied; distances are descriptive and do not certify physical accuracy. No new RF collection, archive write, export, or propagation occurred.

## Verification and evidence

The existing component-owned `test_timing.py` passes, checking that timing fitting preserves fixed position and recovers a known optimum. Runners verify source/input hashes, score replay, fixed-position invariance and track ordering. [summarize.py](summarize.py) checks result provenance and preserves the failed refit explicitly; [summary.json](summary.json) contains the comparison. Both refit outputs and all timing starts are retained. The report inventory is sealed in `evidence.sha256`.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_disjoint_frozen_association -p 'test_timing.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_ds8_union_timing/summarize.py
cd reports/2026_09_29_ds8_union_timing
sha256sum -c evidence.sha256
```

All artifacts are local; this experiment has not been published remotely.
