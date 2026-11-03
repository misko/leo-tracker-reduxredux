# Training with timing marginalized

Tests whether selecting one best timing offset per scan biases the inferred
location relative to integrating timing uncertainty. Uses the same eighteen
four-scan training/whole-scan target splits as the preceding scan-holdout report.
All track likelihoods remain the original q020 mixture; there is no shared
residual-slope model in this experiment.

**Decision: retain the profile-timing baseline.** Of eighteen declared
comparisons, fifteen qualify, two fail numerical precision checks, and one
reaches its wall cap. On the fifteen matched qualified comparisons, location
error improves in9/15 and unseen-scan prediction in8/15, but aggregate predictive
score declines by31.612 and sub-km coverage drops from2/15 to1/15.

## Results and incomplete coverage

Median location movement is5.84m. Twelve qualified fits move by less than40m.
The three movements above300m all worsen geographic accuracy:

| Source four-scan set | Movement m | Profile error m | Marginal error m | Whole-scan log-score gain |
|---|---:|---:|---:|---:|
| DS8 early, first half | 633.76 | 530.21 | 1,063.76 | +77.809 |
| DS8 early, last half | 383.18 | 1,738.69 | 2,116.86 | -116.820 |
| DS9 late, last half | 863.19 | 4,776.00 | 5,139.15 | -0.170 |

![Qualified timing-marginalization effects](comparison.png)

The exceptions remain explicit, and are excluded from BOTH arms of matched
accuracy aggregates:

- DS7 middle, first half: optimizer and derivative checks pass, but changing
  timing quadrature from16 to32 nodes changes the gradient by0.015224, above0.01.
- DS7 late, last half: source fit passes, but one target timing integral changes
  by0.016496 between resolutions, above0.01.
- DS9 middle, first half: the process is killed at the180-second cap. No fitted
  output is available; the receipt retains its initial gradient and timeout.

The excluded DS9 baseline was sub-km. Therefore the matched2/15→1/15 count must
not be presented as a completed eighteen-case comparison or directly compared
to the preceding complete3/18 baseline count. The table preserves unqualified
endpoints and the missing direction; no failure is silently counted as success.

Scalar score replay error is at most3.64e-12 and scalar position-gradient replay
error at most1.01e-7 over all seventeen returned runs. All qualified endpoints
pass the frozen optimizer, derivative, source-integration and target-integration
gates. Final input/source hashes verify. Synthetic tests and Ruff checks pass.
Returned jobs take99.71–170.51seconds; summed returned-job time is2,207.78seconds,
plus the180-second timed-out job, across three workers. No cap is extended again.

This does not rule out externally calibrated timing or a better timing prior.
It does show that replacing profile timing with this uniform-prior integral is
not a supported localization upgrade. The next bounded direction is to test
time-balanced scan selection from the existing corpus: change the observation
geometry available to a fixed model, while reporting the longer elapsed time
span honestly, instead of adding further nuisance flexibility.

## Model and implementation

For each source scan, integrate the product of all TRAINING track likelihoods
over one shared scan time under a normalized uniform[-5,+5]second prior. Sum
the resulting log integrals across the four source scans. Optimize only E/N,
starting at the previously qualified source-only profile-timing baseline.
Held source values and all target values remain outside this objective.

The position derivative of a candidate's Doppler prediction follows the
line-of-sight geometry. For range R, unit direction u, velocity v and receiver
coordinate derivative dr/dx, the frequency derivative is:

    df/dx = (reference_frequency / c) (v - u (u dot v)) dot (dr/dx) / R.

The implementation combines this with the existing Student-t contrast influence
and candidate/background probabilities. It then averages each timing-node
gradient under that scan's normalized timing posterior. This includes mixture
and timing uncertainty rather than freezing a candidate or a best time.
Receiver coordinate derivatives use symmetric site-coordinate differences.

Each source scan replays five timing nodes against the original scalar score
and E/N gradient. Synthetic tests verify this independently of dataset fitting,
check the integrated gradient by finite differences, and mutate held samples
to confirm training score and gradient isolation. The endpoint receives a
16/32-node-per-bank-interval quadrature audit and finite-difference gradient
audit. Every target scan receives the preceding complete-scan timing-integral
test at fixed source-fitted position.

## Artifacts and scope

[Protocol](PROTOCOL.md) freezes the mathematical experiment. The first direction
completed in118.89seconds; [runtime amendment](RUNTIME-AMENDMENT.md) allows
180seconds for each remaining direction without changing the model or fit rules.
`batch.py` excludes that separately run first direction. Per-run files retain
initial and final marginal scores, gradients, optimizer outcomes, timing
integration and scalar replay audits, target integrals, and source/input hashes.
Process receipts retain genuine timeouts and errors. The [table](TABLE.md) and
`summary.json` distinguish missing results from unqualified fits.

This tests a uniform working timing prior, not an external clock calibration.
It is plug-in location prediction: source position uncertainty is not integrated
when target scans are scored. Existing conditional banks and geographic origin
remain in use. Errors refer to the inherited exposed unsurveyed site, and
reciprocal scan halves are dependent evaluations. No new RF collection,
production change, or remote publication is claimed.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_marginal_timing_fit -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120s uv run --no-project --with numpy --with scipy python reports/2026_09_29_marginal_timing_fit/run.py DS7_early_8 0
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_marginal_timing_fit/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_marginal_timing_fit/summarize.py
```
