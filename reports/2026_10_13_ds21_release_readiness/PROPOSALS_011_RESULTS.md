# DS21-011 fitted-only initialization

DS21-011 completed all six initialization stages and exported six physical
proposals for each of CH1–8, CH1–4 and CH5–8. The final shared candidate bank
contains 41 satellites. No reference or held observations were used. This is
initialization coverage, not a final position or an accuracy measurement.

| Stage | Completed work | Stationary fits | Elapsed seconds |
| --- | --- | ---: | ---: |
| Discovery | 100 geographical points; 300 per-view fits | 293 / 300 | 446.480 |
| Doppler shape | Three starts in each view | 9 / 9 | 23.541 |
| Fresh bootstrap | Nine calls; all complete | — | 28.977 |
| Absolute-frequency hybrid | Nine fits at shape proposals | 9 / 9 | 44.451 |
| Cold bootstrap | Nine calls; all complete | — | 28.469 |
| Six-proposal export | 18 physical exports; zero optimizer calls | — | 30.721 |

Stages ran separately with explicit internal and external time bounds. Seven
nonstationary discovery fits remain in the receipts; no failed attempt was
retried. Runtimes include each stage's preparation and exclude separate freeze
commands. The causal catalogue contained 11,129 Starlinks; the regional bank
retained 1,017, built in 4.486 seconds. Discovery selected an initial union of
37 satellites; fresh bootstrap expanded it to 41, retained by cold bootstrap.

Export order is `cold-0`, `cold-1`, `cold-2`, `shape-low`, `shape-high`,
`shape-all`. Maximum source-function closure error is `1.4552e-11 Hz` for
CH1–8 and zero for both halves. Discovery and proposals share information across
views, so these do not constitute independently initialized half-band pipelines.

All new arms use fitted c. The shape projection removes RF-constant offsets;
its fitted-arm label does not establish that it identifies RF calibration.
The subsequent absolute-frequency stage retains fitted c. Hybrid coefficients
remain parent diagnostics and are not substituted for bootstrap exports.

The unchanged reusable initializer is `tools/ds21_fitted_initialization.py`,
commit `7928ec683`, with 402 bound source files including the native binary and
C++ source. Every real stage's source, parent, completion and artifact validators
passed, followed by a final recursive receipt validation. Source/input hashes,
stage counts, timings and export bindings are in
[PROPOSALS_011_RESULTS.json](PROPOSALS_011_RESULTS.json).

Eight of 34 fast development recordings now have complete proposal sets; 26
still require initialization. The matched A/B/C accuracy table still covers
five recordings, plus a separate Model C baseline on DS21-007. DS21-009 and
DS21-011 final model accuracy remains unevaluated. The
[DS21-009 projection diagnostic](PROJECTION_009_DIAGNOSTIC.md) isolates the
generic comparison's current initialization failure. The 20 locked fast cases
remain unopened for inference. The full-DS21 0.5 km target is unmet.
