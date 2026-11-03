# DS8 recording groups favor different locations on held observations

**The DS8 sampling discrepancy persists after both fixed locations are evaluated on the same recordings with training-only timing refits.** The sixteen original-only recordings favor the earlier location on held data, whereas the sixteen rank-only recordings favor the later location. The eight common recordings are evenly split. This supplies a recording-dependent model-consistency problem, not evidence that a single universal timing correction resolves it.

The two endpoints come from the earlier and rank-selected N24 fits, separated horizontally by 2.078 km. Their reported reference distances were 390 m and 1,877 m respectively, but no reference coordinate enters this diagnostic. It compares their predictive support, not independently known position truth.

| Recording group | Scans | Training score: rank minus original | Held score: rank minus original | Held scans favoring rank | Top-candidate changes / tracks |
|---|---:|---:|---:|---:|---:|
| Shared | 8 | +87.63 | −11.90 | 4/8 | 20/483 |
| Original-only | 16 | −528.49 | −408.30 | 3/16 | 12/951 |
| Rank-only | 16 | +234.59 | +245.57 | 11/16 | 18/936 |
| Full union | 40 | −206.26 | −174.63 | 18/40 | 50/2,370 |

Positive margins favor the rank-selected position. Unlike comparing scores from unequal source panels, each margin compares the same observations under both positions. Aggregates are sums of log scores; scans differ in observation count and information, and neither scans nor tracks are asserted independent.

The shared eight scans do not provide a decisive held preference for the shifted location. The rank-only group's positive held margin also means the adverse reference-distance result is not simply explained by its location fitting random training noise while uniformly losing held prediction. Interleaved held samples inherit upstream selection and are not an independent site-validation set.

Only about 2.1% of tracks change their conditional top candidate between the two scored endpoints. Most retain the same top component while the geographic compromise changes. This argues against explaining the entire discrepancy solely by visible top-candidate switching. It does not verify identities, exclude incorrect candidates shared by both endpoints, or show that unchanged mixture weights and responsibilities carry the same information.

## Frozen method and validation

The [protocol](PROTOCOL.md) preceded execution. Verify byte-identical input artifact digests for the eight common recordings, then construct the union once. Retain all original masks, observations, candidate banks, q020 likelihood and zero-height model.

At each fixed geographic endpoint, fit each scan's timing independently using training data. Starts comprise the best of the existing 41-point timing grid and all available inherited timings from the original and rank N24 fits, deduplicated by exact value. The existing timing-only optimizer holds position fixed and applies unchanged convergence, boundary, gradient and finite-difference checks. Highest qualified training score selects timing; held values are used only afterward.

All **80 scan/location cases** have a qualified selected timing, so all 40 scans contribute both predictions. Of 176 starts, 162 qualify; the 14 unqualified starts remain in the evidence without retry or threshold relaxation. Maximum finite-difference gradient discrepancy across starts is 1.61e-6. Position immutability is asserted for every selected result. Visible-candidate counts do not change for any track between the scored endpoints; that count check is not a claim of globally invariant visibility support.

Execution completed in 54.9 seconds within the 180-second cap. Each scan is checkpointed in `scans/`; [results.json](results.json) preserves every start, selected timing, paired score and candidate-change count. Source and input bindings verify, including the inherited rank-control freeze. The reused timing optimizer already has a component-owned synthetic test for fixed position and correct timing recovery; this diagnostic introduces no new timing estimator.

## Consequence and next discriminating step

Keep the two endpoint evaluations separate from a new location fit. The complete union favors the earlier endpoint on held score, but neither endpoint was optimized on that union, and selecting a location from these exposed held scores would not constitute independent calibration.

A useful follow-up is a joint fit of all forty recordings, initialized from both existing endpoints, with the same frozen likelihood. That can distinguish an intermediate compromise from persistent competing modes and show the cost of additional recordings. It would be an explicitly exploratory extension with a larger scan budget, not an improvement at the original 24-scan budget. Diagnose which scan contributions oppose the fit before introducing further free clock/orbit or reliability parameters.

This analysis identifies conflicting recording-group support, not its physical cause. Receiver/timing/propagation error, wrong associations and source-selection artifacts remain possibilities. The operator reference's independent uncertainty is unresolved. No new RF, archive export, production change or remote publication occurred, and reliable absolute subkm accuracy remains unverified.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 timeout --kill-after=10 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_ds8_sampling_diagnostic/run.py
```

Use a fresh output context; checkpoints and final results use exclusive creation. `evidence.sha256` seals the protocol, runner, per-scan evidence, aggregate results and report. Original observation files and prior reports remain unchanged.
