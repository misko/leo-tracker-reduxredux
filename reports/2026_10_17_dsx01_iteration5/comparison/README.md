# DSX01: complete development protocols and prediction checks

The largest requested-window count is now 462/693, versus 96/693 originally,
with eight windows descriptively restoring at least 80% of their originally
missing support. That model fails conditional temporal prediction. None of
these results establishes the requested generalizable localization improvement,
and no model is promoted.

This snapshot reads the saved complete protocols only. It does not choose a
different model, satellite or prior per window. There are 15 frozen windows
and 20,084 original winning observations across five scans. Original satellite
labels and the configured station position are diagnostic references, not
independent identity labels or surveyed geographic truth.

| Fitted-c development protocol | Requested /693 | ≥80% net-restored windows /15 | Full /20,084 | New / lost original full support |
|---|---:|---:|---:|---:|
| Original | 96 | 0 | 11,222 | 0 / 0 |
| Fixed exact profile | 422 | 6 | 13,784 | 3,304 / 742 |
| Expanded exact profile | 434 | 7 | 14,248 | 3,817 / 791 |
| Fixed + frequency-width continuation | 455 | 7 | 14,173 | 3,988 / 1,037 |
| Expanded + frequency-width continuation | 429 | 5 | 14,455 | 4,302 / 1,069 |
| Constant-Hz residual, sigma=1000 Hz | 462 | 8 | 14,372 | 3,929 / 779 |

Every new/lost count above is normalized against the original published
fitted-c assignments. In component reports some new/lost counts instead use
their immediate matched control; those are different comparisons. The table
describes complete protocols with different search histories, candidate counts
and nuisance dimensions. Causal claims about an individual change must use its
component's matched-budget control, not arbitrary adjacent table rows.

![Frequency coverage and configured-reference position distance](performance-fitted-c.png)

The left curve improves considerably; the right curve still leaves three of
five scans very far from the configured station. A better frequency fit has
not solved localization. Unassigned observations remain in the left denominator;
all five recordings remain in the right denominator. Numerically nonstationary
endpoints remain visible and are flagged in `comparison.csv`.

![Every requested window, original and complete protocols](windows-fitted-c.png)

Window003 stays 0/27. The apparent strongest model's eight restored windows are
001/005/007/008/009/010/013/015. These are descriptive assignment counts, not
verified satellite identifications. Its paired original/variant RMS is
156.884→144.034 Hz on the same retained rows, with identity changes allowed.

## Negative prediction evidence

The constant-Hz residual model learns only its new per-satellite b_s on one
temporal half, keeping the same full-data-conditioned geography, calibration
and detection probabilities fixed, then predicts the opposite half. Across
both c arms and widths, 39/40 tests worsen actual excluded-row likelihood.
For fitted-c and sigma=1000 Hz, pooled full support falls from 13,784 to
8,307/20,084, and requested support from 422 to 262/693. This rejects stable
temporal correction under that baseline despite the full-data count gain.
It is conditional residual validation, not an end-to-end cold-pipeline test.
See the [sealed component report](../../2026_10_17_dsx01_iteration4/frequency_bias/README.md).

The separate faithful S03 first-half cold pipeline learns all candidates and
calibration from training probes. Its train support is 1571/2006; held support
is 165/1982. A diagnostic comparison against original full-data labels finds
1190/1410 original held assignments have winner IDs absent from the cold bank.
That explains much of the forecasting loss without treating the original
labels as truth. Constant-clock extrapolation, affine drift and geometry/timing
confounding remain additional concerns. The next alternating-block assay tests
gap interpolation across the capture separately; it must not silently replace
or relabel the negative forecasting test.

## Timing and c sensitivity

[Same-215-pair timing histograms](../../2026_10_17_dsx01_iteration4/frequency_bias/timing-histogram-fitted-c.png)
retain common and relative timing separately. The new
[element-age audit](../age_audit/README.md) finds 71/215 original relative shifts
above 10 seconds, little descriptive age correlation, and approximately 73 km
of native orbital motion per 10-second shift. Fitted shifts are not physical
TLE-error labels. Historical age-prior calibration is separate and excludes
DSX radio measurements and reference positions.

The matched component c=0 sensitivity outcomes remain explicit. The additional
summary plots below aggregate their saved complete protocols; cross-protocol
seed/search differences still apply. The original reference in CSV accounting
is the published fitted-c baseline, not a newly invented c=0 original run.

![c=0 frequency and position curves](performance-zero-c.png)

![c=0 requested-window counts](windows-zero-c.png)

Reproduction: `render.py` reads frozen source receipts, confirms source-ordered
timestamps, checks exact observation IDs where exported, and binds every JSON
and NPZ input in `receipt.json`. Older scientific NPZ exports omit observation
IDs; their original source ordering and provenance receipts remain the authority.
The two component tests verify loss-debited restoration and reject row-shape
mismatches. This renderer performs no scientific fitting. See
[the validation contract](../VALIDATION.md) for inference and completion gates.
