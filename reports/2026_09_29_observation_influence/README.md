# Training-observation influence on position

The previous waveform correction budget mostly sampled observations with little
influence on position. A training-only ranking identifies a more informative
equal-size budget: eight observations per panel capture **4.25–16.79%** of the
model's summed squared position response, versus at most0.42% for the previously
corrected eight. This is a sensitivity result, **not an accuracy improvement**.

All nine panels passed Hessian, derivative and small-perturbation refit checks.
The [frozen queue](queue.json) contains72 observations from29 tracks,21 recordings
and72 distinct source visits. None overlaps the72 earlier corrections. This is
an existing-corpus reanalysis queue; no new RF collection is requested or run.

![Equal-budget sensitivity comparison](comparison.png)

| Panel | Previous squared-response share % | Ranked share % | Largest response m/canonical Hz |
|---|---:|---:|---:|
| DS7 early | 0.418 | 10.394 | 0.579 |
| DS7 middle | 0.002 | 4.249 | 0.202 |
| DS7 late | 0.320 | 6.987 | 0.269 |
| DS8 early | 0.090 | 11.739 | 0.353 |
| DS8 middle | 0.011 | 16.787 | 0.789 |
| DS8 late | 0.001 | 12.221 | 0.464 |
| DS9 early | 0.068 | 7.123 | 0.388 |
| DS9 middle | 0.001 | 5.137 | 0.292 |
| DS9 late | 0.002 | 11.057 | 0.807 |

Shares use all training observations as the denominator, including rates outside
the current waveform assay. The ranked queue is restricted to >=5MS/s, the
previously tested assay domain. Its rate mix is19 observations at5MS/s,24 at7.5MS/s,
and29 at10MS/s. Both unrestricted and eligible top-eight lists are preserved.

## Calculation

At each cached-arm optimum from the sparse geographic evaluation, compute the
observed negative Hessian of the full q020 mixture score across two position
coordinates and eight recording-time parameters. This includes posterior
candidate ambiguity and the signal/background mixture, rather than freezing
a selected satellite or using an optimistic complete-data information matrix.

For every training observation, analytically differentiate the full parameter
gradient with respect to that observation. The derivative includes changes to
candidate weights and signal responsibility. Solve

```
position/timing response = observed_Hessian_inverse * observation_cross_derivative
```

Rank by the norm of the east/north response, converted to meters per canonical
Hz. Timing remains free through the full matrix inverse. A constant shift across
an entire track has zero position response, as required by the contrast model.
All119,673 training observations across4,328 tracks were evaluated;96,168 were
eligible under the sample-rate restriction.

No held values or reference coordinates were used to compute the ranking. The
fit, retained candidate banks and panel membership are inherited and previously
exposed, so this is not an independently blind dataset or a physical truth claim.

## Validation

The observed Hessian was evaluated with central-difference steps0.001km/0.0001s
and half those steps. Every matrix was positive definite. Maximum relative
symmetry defect was1.02e-6 and maximum relative step disagreement3.25e-5, both
below the frozen0.005 limits. The sum of analytic per-track gradients reproduced
the original full-model gradient within1.85e-12.

For each panel's highest-ranked eligible observation, a ±0.1Hz numerical check
of a one-track model agreed with the analytic observation cross derivative;
maximum absolute discrepancy was2.09e-7, below1e-5. Full-panel refits at ±10Hz
then checked the predicted position response. All18 refits qualified. Maximum
relative response error was2.493%, within the frozen5% tolerance. Detailed
positive/negative fits and audit results are retained per panel.

Three synthetic tests also pass: the mixture cross derivative including changing
weights, prediction gradients, and zero response to a constant frequency shift.

## Interpretation and next experiment

The summed squared responses are a **budget proxy**, corresponding to equal,
independent small perturbation variances. They are not a fraction of Fisher
information, a calibrated uncertainty reduction, or an expected error reduction.
Actual waveform errors can be correlated and biased. A highly influential bad
correction can harm position more than a low-influence correction. The checks
validate a local small-perturbation response, not large corrections or a global
optimum. Only the top observation in each panel received the full-refit audit;
the remaining rankings rely on the same analytic derivatives and checked Hessian.

The next bounded test should read the exact72 queued training excerpts, estimate
the same long-pilot residual without quality-based replacement, preserve the
deployed alias convention, and refit the same full panels with held observations
unchanged. Compare against both cached baseline and the earlier equal-size
budget. Preserve extraction failures and report coverage. Select neither
correction signs nor queue membership using held or geographic outcomes.

This queue has not yet been extracted or corrected. No production estimator
changed, and there is no new sub-kilometer result. The useful outcome is a
numerically validated way to allocate the next small reanalysis budget.

## Evidence and execution

- [PROTOCOL.md](PROTOCOL.md): frozen calculation, ranking and audit rules.
- [queue.json](queue.json): exact source sessions, tracks, observation indices,
  visits, rates, signed responses, ranks and result hashes.
- [summary.json](summary.json), [TABLE.md](TABLE.md): all panel outcomes and audits.
- `DS7_early_8.json` through `DS9_late_8.json`: observed Hessians, unrestricted
  and eligible queues, earlier-budget sensitivities, derivative/refit audits.
- Matching `.npz` files: signed E/N responses for every training observation,
  with document, track and observation indices into the original bound exports.
- `model.py`, `run.py`, `launch.py`, `summarize.py`, `test_model.py`: implementation
  and tests; [receipts.json](receipts.json) records every bounded execution.

All nine commands exited0. Total execution149.13seconds; maximum per-panel19.84s,
below the90-second cap. No IQ was read and no new RF collected. Source and archive
hashes are verified. Use NumPy/SciPy and one BLAS thread for replay; Matplotlib
renders the figure. Reports, queue and evidence are local, not newly published.
