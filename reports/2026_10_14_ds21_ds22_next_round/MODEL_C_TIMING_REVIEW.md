# Model C: versioned worst cases and the next timing test

The bounded Model C experiment uses the already implemented receive-epoch
versus relative-phase control on DS21-039. Its mechanics pass
independent review and 45 synthetic tests. It has no measured DS21 accuracy
result yet. The proposed interpretation is a timing-mechanism sensitivity,
not a demonstrated correction to clocks or TLEs. No numerical DS21/DS22 run,
reference join, or scientific-source modification was performed for this review.
The current requested outcome is sub-kilometre performance on DS21 and DS22,
median error below 0.5 km, and CH1–8 no worse than either half-band estimate.

## Rank within a fixed version

Fitted-c CH1–8 errors below are training-selected, post-seal results. These
cohorts must not be combined into a single ranking by taking the latest or best
result separately for each recording.

| Cohort and fixed method | Largest C error | Second largest C error | Scope |
|---|---:|---:|---|
| Original shared-proposal native C | DS21-023: 4.899 km | DS21-039: 4.291 km | Five completed cases: 001, 003, 005, 023, 039 |
| Generic release original-discovery C | DS21-013: 267.759878 km | DS21-009: 1.595252 km | Four published cases: 009, 011, 013, 025 |
| Coverage-discovery C | DS21-013: 1.846733 km | DS21-009: 1.152329 km | Two published cases only |

Sources: [shared-proposal summary](../2026_10_13_ds21_three_models/README.md),
[009](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md),
[011](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md),
[013](../2026_10_13_ds21_release_readiness/THREE_MODEL_013_RESULTS.md),
[025](../2026_10_13_ds21_release_readiness/THREE_MODEL_025_RESULTS.md),
[coverage 009](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_009_RESULTS.md),
[coverage 013](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_013_RESULTS.md).

DS21-013's original local disks excluded the reference by at least 157.457 km;
the coverage control recovered a useful basin. That is established search
coverage failure, not evidence for an exotic timing correction. DS21-039 is
the more informative timing target: C/all 4.291 km is worse than low 3.759 km
and high 2.557 km, despite a local solution and extensive saved diagnostics.
DS21-023 is the second transfer target for this timing hypothesis, once a
label-neutral control with its own frozen parents is implemented; do not pass
023 through the 039-specific authority facade.

The [pair performance audit](../2026_10_13_ds21_pair_performance.md) concerns
evaluation throughput, not position accuracy. Its roughly 2.9x speed gain
preserved the scored objective. The subsequent repeat improved convergence but
worsened all four matched coupled-model position comparisons. Coupling is not
a promoted fix and should not be reintroduced merely because it is faster.

## What has been established on 039

The original warm refinement improves C/all from 4.291 to 4.073 km; the extra
band calibration extension then worsens it to 4.187 km. Neither achieves the
target. In the saved factorial, timing restores 99.5–99.9% of the NLL increase
caused by prescribed plus/minus 1 km weak-direction moves. That establishes
conditional position/timing compensation. It does not identify bad UTC,
hardware delays, wrong orbit elements, or a justified stronger timing prior.

The finite factorial retains 2,798 training windows, 3,714 native candidates,
43 satellites, fitted c, and the original nuisance priors. Sampling integers
do not change; full adjusted states preserve visibility and only 15–29
satellite/clutter MAP allocations change relative to their endpoint. The
observed weakness is not explained by a broad assignment collapse at those
adjusted endpoints. See the
[factorial report](../2026_10_13_ds21_039_association/TIMING_CALIBRATION_FACTORIAL_RESULTS.md).

RF-unit/end-to-end scaling, sampling-alias invariance, and the prespecified
125 Hz adjacent-cell mechanism have negative audits. Those specific hypotheses
should not be repeated without new contrary evidence. These negative tests do
not validate the entire likelihood or prove all candidate priors harmless.

## Relative-phase implementation review

The current scorer retimes each satellite at `q = t + u + d_k`, including
Earth orientation at q. The alternative evaluates its satellite phase at q
but uses the common Earth orientation at `T = t + u`. Both are coherent
models for different physical mechanisms; neither is established as the true
acquisition mechanism by the existing evidence.

The implementation correctly rotates both ECEF position and velocity by
`G(T) G(q).T`. The velocity transformation preserves the ground-relative
Earth-rotation term. It uses interpolation derivatives rather than assuming
the interpolated position derivative equals the stored velocity. Common and
relative timing derivatives include their respective sidereal-angle terms.
At zero relative shifts, forward predictions and common gradients coincide;
the relative timing gradient differs by the analytically checked rotation
torque. Requiring that relative gradient to coincide would remove the intended
intervention.

The scorer preserves native alternatives/timestamps, calibration frames,
visibility/clutter normalization, satellite bank, fitted c and priors. It
explicitly refuses unsupported temporal families and measured waveform
weights. Exact physical transport, including receiver sampling lifts, supplies
the half-band starts without clipping or calibration projection loss.

Synthetic tests cover independent TEME construction, both generating-mechanism
recoveries, finite-difference gradients, zero-rotation/null controls, transport,
held prediction without a held fit, archive integrity, complete paired seals,
and orphan/failed execution rejection. Independent rerun on 2026-10-14:
**45 passed in 2.13 s**, single-threaded BLAS, using the production scientific
Python environment. No real dataset loader was invoked by this test run.

Remaining limitations matter:

- The exact longitude/common-epoch gauge in degenerate geometry remains. The
  alternative does not supply an independently attested absolute clock.
- Known-ID noiseless recovery is a mechanics check; unknown identities,
  clutter, short scans, and sampling ambiguity can still defeat localization.
- A better residual or different optimum alone does not distinguish real
  orbit phase errors from model flexibility or other calibration mismatch.
- The Python phase predictor and original native predictor have different
  computational paths. Keep the original 20 s/600-iteration budgets and report
  elapsed time, evaluations, stationarity and failures so a runtime limitation
  is not misreported as physical evidence.
- The twelve-fit control saves support and residual diagnostics, but does not
  itself rerun the weak-direction nuisance profiles. A change in confounding
  cannot be claimed from its position results alone.

## Bounded next experiment

Use the reviewed
[relative-phase protocol](../2026_10_13_ds21_039_association/RELATIVE_PHASE_TIMING_PROPOSAL.md)
without a prior sweep: 3 views × 2 conventions × 2 starts = **12 fits**, each
20 seconds/600 iterations; 450 seconds internal, TERM/KILL 480/500 seconds.
Both conventions receive identical starts, candidate sets, local disks and
physical correction functions. Source incumbents are eligible only in their
original receive-epoch convention; they are not unscored phase fallbacks.

The actual original seven-call parent paths are:

```
reports/2026_10_13_ds21_039_root_cause/local/refinements-v1/freeze.json
reports/2026_10_13_ds21_039_root_cause/local/refinements-v1/fits/terminal.json
```

The root coordinator should choose a new output namespace, publish the frozen
protocol and schedule its existing `relative-phase-run.py` entrypoint through
the bounded numerical queue. Do not overlap it with an unbounded campaign or
change live frozen sources. All twelve outcomes must be sealed before the
existing evaluator projects held blocks or imports reference coordinates.

The result table must show all/low/high position errors under each convention,
the all-minus-low and all-minus-high differences, and separate held likelihood
and convergence outcomes. The desired combined estimate is no worse than
either half, but reference error must not choose a per-case convention or
fallback. Success on 039 is insufficient to claim DS21 or DS22 success.
The existing half-band results inherit shared discovery/initialization. They
are conditional channel-view controls, not independent half-only pipelines.
The final requested comparison must separately run CH1–4-only and CH5–8-only
discovery, candidate construction and initialization, and distinguish those
results from the historical shared-proposal half views.

At report completion, the root coordinator reports that the 332-source freeze
at `root_cause/local/relative-phase-v1` has completed and the bounded twelve-call
run has started. The updated proposal is published at main commit
`8cacd80d9`. No completed fit or accuracy result from that run is asserted here.

## Additional causal discriminator, if needed

A separate new, source-frozen diagnostic can compare the already saved
18 factorial states under both conventions: **36 objective/gradient calls,
zero fits**, a proposed 90/105/110-second envelope, no held/reference access.
Reuse the saved endpoint and displaced vectors exactly, including their
calibration/timing blocks. Keep fitted c and the 43-satellite bank; do not
estimate new weak directions from reference errors. Existing original
18-state values must replay before interpreting the new condition.

For each endpoint/sign and convention, report geography-only minus endpoint,
timing-only minus geography, full minus endpoint, timing rescue fraction where
the geography-only increase is positive, and joint/native/satellite posterior
changes. No fraction is defined for a nonpositive denominator. The phase
endpoints here are prescribed states, not stationary phase minima.

If nearly complete compensation persists, separating Earth orientation from
satellite phase is not sufficient to explain this saved finite weak direction.
If compensation changes materially, this identifies a model-mechanism
sensitivity requiring the twelve-fit control and eventual transfer validation;
it does not prove a timing fault. Do not substitute a fixed-responsibility
Fisher matrix for the observed marginal likelihood or claim calibrated error
bars. The existing observed-curvature component can be reused for a separately
bounded post-fit investigation if needed; new curvature infrastructure is not
required now.

No DS22 input or accuracy result was inspected in this review. Promotion to
DS21/DS22 requires a single frozen algorithm/selection rule, the same matched
channel views, explicit failures in the denominator, and the root-owned
development/locked evaluation plan.
