# Formal positioning model and archived-data benchmark

Follow-up: the [breakthrough summary](2026_09_21_positioning_breakthroughs.md)
and [four-factor ablation / 1/32-data benchmark](2026_09_21_position_ablation_report.md)
add 258 new fits, including all 16 model-switch combinations and explicit
sparse-data convergence failures.

The formal fixed-identity model reached **328 m horizontal error** on the
archived 622-track campaign, using strictly pre-capture orbital information.
This improves on the approximately 4.86 km strict fixed-orbit baseline, but does
not improve on the earlier exploratory 275 m result. It is a conditional replay
at one known evaluation site, not demonstrated sub-kilometre accuracy at new sites.

The work also found two important failures: local uncertainty is overconfident,
and a distant-start optimizer could stop with its noise scale pinned to the
upper bound. Both are recorded rather than hidden by reporting only the best
position estimate.

## What is implemented

- A pure numerical orbital model with one correction rate per satellite,
  per-segment frequency offsets, normalized robust likelihood, within-track
  correlation, and a measurement scale learned from each fit's own observations.
- Strict causal preparation: both orbital epoch and catalogue availability must
  precede capture; orbital-phase sensitivity is separate from receiver-clock
  sensitivity. No-history satellites retain their actual TLE ages.
- Deterministic nested density and whole-pass subsets, duration prefixes,
  independent solver starts, source/input hashes, and complete failure accounting.
- Evaluation of horizontal error and local uncertainty, with independent
  simulation coverage and explicit handling of unsupported evaluation rows.
- A research identity-mixture extension sharing orbit corrections by satellite,
  with an unassigned component and identical correction priors for candidates.

Satellite identities in the fixed-identity benchmark are inherited from the
full historical RF analysis. Its reduced-data runs test conditional positioning,
not acquisition of both identities and location from a fresh small dataset.
Receiver altitude and clock are fixed; uncertainty in these inputs is not
included in the local ellipse.

## Main evidence

| Experiment | Result | Interpretation |
|---|---|---|
| Strict fixed-orbit baseline | approximately 4,859 m; 157.09 Hz randomized held-out RMS | Reference, fixed UTC |
| Earlier exploratory orbit correction | approximately 275 m; 78.63 Hz | Historical comparison, different nuisance treatment |
| Formal model, sealed local replay | 328.0 m; 86.59 Hz | Sub-kilometre archived point error |
| Exact SGP4 versus phase approximation | 0.00716 Hz RMS; 0.10433 Hz maximum | Passes frozen 0.2 Hz maximum tolerance |
| Local nominal 95% region | 45 m major semiaxis, misses truth | Not calibrated for operational use |
| 100 model-consistent simulations | 91/100 nominal 95% regions cover truth | Limited coverage evidence |
| 100 simulations with additional drift | 82/100 nominal 95% regions cover truth | Omitted systematic effects matter |

Ground truth, 37.84903264307456°, −122.4856541910174°, is used by the evaluator
after fitting. It does not choose satellite identities, orbital priors, solver
starts, or subset membership. Randomized held-out frequencies are used only for
residual evaluation, not fitting or model selection.

## Detailed reports and artifacts

The final paired matrix contains 176 model/subset runs. All 88 strict-baseline
fits converged. Formal fitting converged on 63/80 seeded subsets, the full
dataset, and all seven duration prefixes. The table below reports errors only
for converged fits and retains the success denominators alongside them.

| Available fitting data | Formal median error | Converged formal runs | Baseline median error |
|---|---:|---:|---:|
| Exact quarter of observations | 399 m | 11/20 | 4,893 m |
| Exact half of observations | 373 m | 13/20 | 4,838 m |
| Quarter of whole passes | 896 m | 20/20 | 5,205 m |
| Half of whole passes | 444 m | 19/20 | 5,234 m |
| Full dataset | 328 m | 1/1 | 4,859 m |

Keeping observations spread across passes helps more than retaining the same
number of observations from fewer passes on this cohort. Whole-pass quarter
errors range from 281 m to 2,009 m. The formal duration results are also not
monotonic: 5.15 km at 30 minutes, 1.46 km at one hour, 2.14 km at two hours,
403 m at four hours, and 498 m at eight hours. This is evidence about geometry
and subset sensitivity at this site, not a universal time-to-fix curve.

Seventeen seeded formal runs failed the nuisance convergence check. Increasing
the inner iteration budget from 60 to 240 on one failed quarter did not recover
convergence, so the failures are not silently converted into valid fixes.

![Paired sample-size benchmark](artifacts/2026_09_21_position_subset_benchmark/benchmark-final.png)

- [Formal model, sealed fit, and exact propagation verification](2026_09_21_formal_orbit_model.md)
- [Paired full/half/quarter and duration benchmark](2026_09_21_position_subset_benchmark.md)
- [Synthetic uncertainty coverage, all 200 trials, and figure](2026_09_21_formal_position_characterization.md)
- [Matched shared-orbit identity-mixture experiment](2026_09_21_shared_identity_orbit.md)
- [Model equation and approximation specification](../docs/research/formal-orbit-model.md)
- [Implementation and validation plan](../update_model.md)

## What would establish a reliable sub-kilometre fix

The separate identity-mixture prototype converged but did not improve its
matched fixed-identity reference: error changed from 2,007 m to 2,040 m while
held-out RMS decreased from 83.03 to 80.99 Hz. Its noise and nominal orbital
prior differ from the formal model; this is not evidence that adding identity
uncertainty to the formal 328 m model would necessarily worsen it. It shows why
we must compare matched models and evaluate position, not just residual RMS.
That prototype also fails its exact-propagation tolerance and cannot certify
its omitted-candidate support with the conservative bound used here. It remains
an explicitly unqualified research experiment.

The next scientific requirement is calibrated performance across independent
campaigns and receiver positions. Overlapping subsets from one site cannot
establish a population 95th-percentile error. The model also needs clock and
receiver-drift uncertainty tied to measured continuity evidence, and a combined
identity/noise treatment verified against the full candidate population.

Small residual RMS is useful but insufficient: an orbital correction can absorb
part of a position error, while omitted systematic effects can bias many tracks
in the same direction. A narrow local curvature ellipse measures uncertainty
within the assumed model; it does not account automatically for those errors.

The next model comparison should test whether one rate per NORAD remains valid
across distinct TLE updates, and whether a constrained receiver drift explains
the residual structure. Each additional freedom must be evaluated with the same
causal inputs and training-only selection: otherwise it can improve RF residuals
while weakening position identifiability. Independent campaign checks should
precede any claim that the reported uncertainty is calibrated.

This work uses archived data only and does not change production scanner
configuration, capture cadence, or the processing queue.
