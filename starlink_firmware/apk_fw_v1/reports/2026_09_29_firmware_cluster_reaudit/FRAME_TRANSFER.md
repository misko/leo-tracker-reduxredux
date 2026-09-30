# Do early-symbol groups reproduce in a separate frame?

A modest upper-edge signal survives this exploratory test: an eight-group model
has 19.2% held-out balanced accuracy, versus 15.4% under conditional shuffles.
It survives the specified multiple-comparison controls. This supports limited
repeatable waveform structure, not a firmware field or satellite identifier.

## Design

Use the 1,393 deduplicated qualified DS7/DS8/DS9/DS10 entries. Verify every soft
artifact SHA256 against its metadata. Extract symbols 2–7 at four common nonpilot
carriers. Convert complex values to unit phase, concatenate real and imaginary
coordinates, subtract each vector's own mean and normalize it. No identity labels
or target-frame population statistics enter the features.

Earlier saved dendrograms average both reserved frames; using those labels to
evaluate either frame would leak evaluation data. Instead, fit new average-linkage
trees using **only the first reserved frame**, separately for upper and lower
edges, and freeze cuts at 2, 4 and 8 groups. Assign each second reserved frame to
the nearest discovery-group centroid. Macro-average recall across discovery
groups so the large majority group cannot manufacture high accuracy. The same
centroid rule fits discovery labels at 95–100%; the much lower held performance
is not simply failure to represent the discovery hierarchy with centroids.

Controls permute held predictions within exact session/channel/rate/receiver
strata. Separate circular controls rotate the predictions within chronological
stratum order, preserving that order except at the wrap. There are 499 controls
of each type. Only 159/438 upper and 546/955 lower observations belong to strata
with more than one observation. Singleton strata cannot supply exchangeability.
Pilot coherence remains a quality proxy; these controls do not establish matched
SNR, independent channel calibration or independent receiver noise.

For each test, center the complete 500-member reference set (observed plus 499
controls) symmetrically. Use the maximum centered score across the six edge/cut
tests for family correction. A completely constant reference set abstains rather
than contributing a large fixed baseline. This centered formulation replaced an
initial unsuitable maximum of raw chance-adjusted scores: the latter was dominated
by a stratum-frozen lower-edge partition and concealed the control's lack of power.
The correction was methodological, not a change to observations or fitted groups;
the resulting p-values remain exploratory and need further independent validation.

## Results

| Edge / groups | Held balanced accuracy | Mean conditional shuffle | Family shuffle p | Family circular p |
|---|---:|---:|---:|---:|
| Upper / 2 | 0.526 | 0.493 | 0.214 | 0.262 |
| Upper / 4 | 0.249 | 0.235 | 0.246 | 0.302 |
| Upper / 8 | 0.192 | 0.154 | 0.016 | 0.022 |
| Lower / 2 | 0.613 | 0.613 | Untestable | Untestable |
| Lower / 4 | 0.296 | 0.295 | 0.896 | 0.886 |
| Lower / 8 | 0.173 | 0.164 | 0.294 | 0.344 |

The upper eight-group sizes are 322, 34, 30, 8, 17, 14, 9 and 4. This is not
eight balanced protocol classes, nor evidence for a three-bit field. Its modest
excess could reflect recurring header content, residual channel response or other
within-observation structure not removed by the controls. The two frames come
from the same short excerpt and share synchronization machinery. Previously
inspected recordings provide a computational holdout, not new prospective data.

The lower two-group case is explicitly a coverage limit: its score does not vary
under either control, so it cannot support a significance conclusion. The apparent
61.3% accuracy must not be treated as evidence that it outperforms the conditional
baseline, nor as a negative result about the existence of a field.

## Connection to firmware evidence

The prefix audit establishes mode-dependent field presence and bit widths in
software. This experiment has no mode labels or verified RF-to-prefix transform.
Thus the upper lead is a candidate association to trace, not a field assignment.
Its next discriminating checks should ask which coordinate relationships and
recording conditions contribute, then test transfer across receivers or visits.
The current result does not justify a new arbitrary byte-offset, CRC, or decoder
scan. No SATAddr/NORAD relation is inferred.

## Reproduction and validation

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/frame_transfer.py
uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_frame_transfer.py
```

The ignored result contains source/method hashes, all discovery memberships,
group-wise held recall, control maxima and coverage counts. Tests check majority
imbalance, amplitude invariance, and exclusion of a constant control from family
maxima; both pass, as does Ruff. Original artifacts and scientific fixtures are
unchanged. No new RF or data commit occurred.
