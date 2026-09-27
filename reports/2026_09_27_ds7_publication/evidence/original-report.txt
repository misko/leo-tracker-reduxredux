# DS7 full88 final benchmark

The frozen joint estimator achieved **677.323 m horizontal error**, using all
88 DS7 recordings spanning **10 h 19 min 59 s**. It converged without hitting a
position or timing boundary. This meets the complete pooled benchmark in
[the specification](FULL88-SPEC.md).

The reference is operator supplied and unsurveyed, and this single site was
exposed during development. This result does not establish surveyed accuracy,
accuracy at unseen sites, or sub-kilometre accuracy for individual recordings.
The inherited DS6 coordinate already has 809.029 m error without DS7 observations;
the joint result improves that distance by **131.706 m (16.28%)**. This comparison
does not isolate the contribution of observations from inherited site knowledge.

## Complete pooled comparison

| Frozen method | Qualified / attempted | Horizontal error | Outcome |
|---|---:|---:|---|
| Joint static Doppler mixture | 1 / 1 | **677.323 m** | Converged; no boundary |
| Equal spherical mean | 0 / 1 | — | Abstained: unqualified upstream estimate |
| Inverse training-RMS² mean | 0 / 1 | — | Abstained: unqualified upstream estimate |
| Lowest training-RMS 75% mean | 0 / 1 | — | Abstained: unqualified upstream estimate |

All controls retain the required 88-source denominator. Recording `single-062`
hit the east +12 km boundary, so the controls could not qualify. It was not
dropped. The joint model instead consumes all 88 frozen observation/bank inputs
directly; it does not aggregate the independent positions.

The estimated coordinate is 37.854429757806905, -122.48938804955883. Predictions
were sealed before the coordinator scored them with the unchanged great-circle
metric (mean Earth radius 6,371,008.8 m). See the [sealed score](coordinator/joint-score-v1/scores.json)
and [run inventory](solver/joint-v1/seal.json).

## Individual recordings and chronological panels

All 88 independent estimates were evaluated: **87 qualified**, one hit a
boundary, and **13 of 88** were below 1 km (13 of 87 qualified). Eight qualified
estimates improved on the inherited 809 m coordinate. Median error was
**2,571.168 m** across all returned positions and **2,515.151 m** among qualified
positions. The range across returned positions was 402.815–15,644.019 m; the
maximum belongs to the unqualified boundary estimate.

The [complete individual outcome ledger](../2026_09_27_ds7_wave9/coordinator/coverage88-final.json)
retains all scores, flags, session identifiers, and source hashes. The
[eleven chronological panel comparisons](group-panels-v1.md) retain all four
methods and all 88 recordings. Only 3 of 11 joint panels were below 1 km;
their median error was 1,429.43 m. The first panel remains 2,541.48 m, and the
original prefix-four loader failure remains recorded in that comparison.
These overlapping single-site budgets are not independent generalization trials.

## Method, provenance, and validation

The run used the unchanged wave-4 batched joint model: Student-t likelihood
(four degrees of freedom, 100 Hz scale), stationary per-track frequency offsets,
finite candidate mixture, inherited DS6 spatial prior, ±12 km position bounds,
and ±5 s recording-specific timing bounds. Timing banks have 41 quarter-second
grid points. Three frozen timing starts (0, -2, +2 s) all converged inside the
bounds, using 65 objective evaluations in total. Selection used training
likelihood; the +2 s start won. Geographic errors did not select the start.

There were **5,131 eligible tracks** across all 88 recordings and 11 predeclared
track exclusions: five with fewer than two training observations and six with
no held-out observation. No recording was excluded. Training conditional RF RMS
was 625.227 Hz; this is not an accuracy or held-out validation claim.

The [input audit](../2026_09_27_ds7_wave9/inputs/INPUT-INTEGRITY.md) verified exact
plan membership and 264 artifact hashes. The minted dataset digest is
`47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.
The [launch receipt](solver/full88-joint-bound-receipt.json) binds the inputs,
plan, scientific configuration, code, and execution limits. Model configurations
are under [config/ds7](../../config/ds7/); frozen dataset membership lives in
dated report directories indexed by [datasets.md](../../docs/research/datasets.md).

The unchanged implementation previously passed **91 relevant tests and Ruff**;
its validation response was byte identical to the earlier implementation. See
[wave-4 validation](../2026_09_27_ds7_wave4/RESULTS.md). The final closeout records
current evidence hashes and the independent verification of earlier wave bindings.

## Resources and supplementary diagnostic

The joint adapter took **1,480.174 s**; outer wall time was **1,488.76 s**, within
the frozen 1,800 s adapter / 1,920 s outer budgets. It used one CPU/BLAS thread,
nice 19, and an enforced 8 GiB address-space ceiling. A live adapter high-water
snapshot was 6,022,212 KiB (5.74 GiB). Exact final adapter peak memory and total
CPU time were not measured: outer GNU time's memory/CPU counters cover its
privilege wrapper and must not be attributed to the adapter. The
[terminal receipt](solver/joint-v1-terminal-receipt.json) preserves this limitation.
Each control completed in under 0.1 s. No new RF collection or raw-IQ processing
was used for this run.

The supplementary all-88 fixed-prediction residual audit **failed** after
60.31 s, exit 1, with 5,977,144 KiB maximum RSS. Its unchanged program rejects
the required boundary estimate for `single-062` with
`ValueError: audit requires a qualified frozen estimate`. The attempt produced
no residual result and was not retried. The [failure qualification](residual/RESULT-QUALIFICATION.md)
and [terminal receipt](residual/fixed-prediction-audit-terminal-receipt.json) are
retained. No held-out residual validation is claimed. This separate diagnostic
failure does not change the sealed joint location score.

The earlier completion-gate and next-options reviews are historical planning
documents. This report and the final closeout record the terminal outcome.
Further work should target individual-recording reliability and an independent,
surveyed-site evaluation before making broader accuracy claims.
