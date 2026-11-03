# Whole-receiver geographic transfer

Fit one receiver's training measurements, then evaluate all tracks on the other
receiver without refitting position or recording time. This is a stricter
measurement split than the preceding interleaved-point tests, intended to test
whether shared-slope model improvements reflect better geographic estimates.

**Decision: keep the baseline; retain the smaller shared-slope prior as a
candidate for whole-scan validation.** It improves opposite-receiver score
in12/18 directions, but geographic error in only9/18. The larger prior has
worse aggregate transfer and fewer sub-km results.

## Results

All18 receiver directions complete; all54 selected model fits qualify.

| Measure | Source-only baseline | Slope SD0.5 Hz/s | Slope SD2 Hz/s |
|---|---:|---:|---:|
| Source interleaved held-score improvements | Reference | 18/18 | 18/18 |
| Opposite-RX complete-track score improvements | Reference | 12/18 | 9/18 |
| Geographic error improvements | Reference | 9/18 | 5/18 |
| Sub-km receiver-only fits | 4/18 | 5/18 | 3/18 |
| Summed opposite-RX log-score change | 0 | +159.911 | -292.899 |

The sums are descriptive scores over dependent reciprocal directions, not
independent-trial significance tests. Sub-km counts refer to one receiver's
eight-scan fits, not the earlier combined-receiver panel results.

Median error over the three panels in each source-receiver/dataset stratum:

| Dataset | Source RX | Baseline m | SD0.5 m | SD2 m |
|---|---:|---:|---:|---:|
| DS7 | 0 | 1,840.19 | 1,858.29 | 2,087.80 |
| DS7 | 1 | 2,495.51 | 2,761.03 | 3,139.37 |
| DS8 | 0 | 1,413.02 | 1,369.64 | 2,544.50 |
| DS8 | 1 | 1,087.89 | 1,038.26 | 950.09 |
| DS9 | 0 | 1,440.51 | 1,307.56 | 2,028.13 |
| DS9 | 1 | 3,818.17 | 3,644.11 | 3,102.02 |

![Source prediction gain versus opposite-receiver transfer](transfer.png)

The small prior's partial transfer is more useful than its universal source
interleaved score improvement, but does not overturn the previous combined-RX
geographic failure. Both receivers can share timing, orbit, processing and
association errors. Whole-scan validation should therefore precede promotion,
using a target-scan timing model that does not fit away geographic errors on
the scored observations. No further prior scale is selected from these errors.

All final input/source hashes verify. The largest selected-fit derivative-audit
discrepancy is2.38e-6; the largest quadrature discrepancy across score, gradient,
and held score is0.000848, below0.01. Each direction finishes within28seconds;
summed process wall time is366.15seconds across three workers. Ruff and the
receiver-isolation test pass.

## Split and scoring

For each of nine eight-scan panels, run RX0→RX1 and RX1→RX0. Each direction
fits the q020 baseline from three fixed starts (-2,0),(0,0),(2,0)km, relative to
the existing configured origin, with zero timing offsets. Selection uses source
training score only. Combined-receiver optima are never used as starting points.

Two shared-slope variants start at that source-only optimum, with fixed0.5 and
2 Hz/s prior scales. Group membership comes only from the source baseline's
training probabilities. All alternatives and unassociated-track components
remain in the mixture. See the preceding shared-candidate-slope report for
the normalized joint likelihood and its explicit truncated prior.

Source held scores use the original interleaved split and each arm's own model.
Target scores use the ORIGINAL q020 likelihood on the opposite receiver's
complete observation vectors, at the source-fitted E/N and eight timing
offsets. The target receiver contributes no parameter fit, start selection, or
group assignment. All target tracks are scored, including observations formerly
marked training. The target score is the training log density plus conditional
held log density, giving the complete-vector log density under the same retained
candidate visibility gate. Frequency constants remain integrated through
contrasts, not fit from the target's scored data.

This comparison measures geographic/timing transfer under a fixed evaluation
model. It is not a full cross-receiver predictive distribution for a latent
slope model, since slopes are not transferred to target candidate components.
It is also not complete RF blindness: existing candidate-bank exports,
visibility gates, time spans, and configured geographic origin are inherited.
Both receivers share the same site, collection times and possible systematics.

## Artifacts and verification

[Protocol](PROTOCOL.md) fixes the split, starts, model widths, and numerical
qualification rules. [Full table](TABLE.md) includes both directions, all models,
qualification, geographic error, source held gains, and target full-track gains.
`summary.json` retains all results and any missing or unqualified directions.
Per-direction artifacts retain every baseline start and numerical audit,
optimizer messages, parameter vectors, timings, track counts, and input/source
hashes. Receipts record process exit status. `batch.py` excludes the first
direction, which is run separately as shown below.

The isolation test mutates the opposite receiver's measurements and verifies
that the source score and gradient remain unchanged, while the target score
changes. Reused shared-slope tests cover normalized joint integration,
zero-slope baseline equivalence, derivatives and interleaved held isolation.
Reference coordinates are accessed only by the post-fit summary.

Errors refer to the inherited exposed, unsurveyed location; this does not measure
generalization to a new site. Reciprocal receiver directions are dependent.
Do not equate improved source held prediction with a physical accuracy gain.
No new RF, production changes, or remote publication occurred.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_receiver_holdout -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120s uv run --no-project --with numpy --with scipy python reports/2026_09_29_receiver_holdout/run.py DS7_early_8 0
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_receiver_holdout/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_receiver_holdout/summarize.py
```
