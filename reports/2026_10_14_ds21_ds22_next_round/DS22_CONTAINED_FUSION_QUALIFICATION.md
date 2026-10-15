# Native-C fusion regressions inside reference-containing search domains

Exact half-state transport qualifies for DS22-109 and DS22-131 without changing observations, candidate banks, calibration functions, satellite timing, receiver alias representatives, or physical priors. The comparison evaluates each complete half-derived state under the original full-band objective, before any new optimization. All estimates use fitted c.

| Case | Original full objective | Low-derived state under full objective | High-derived state under full objective |
|---|---:|---:|---:|
| DS22-109 | 43565.507238 | 37766.046118 | 36600.939496 |
| DS22-131 | 36903.016133 | 38886.430539 | 40641.781517 |

Both transported states already improve the full objective for 109; the high-derived state improves it by 6964.567742. This is direct evidence of a missed feasible basin in the original full-band search. It is not yet an accepted full-band estimate: stationarity under the source half objective is not stationarity under the target full objective. For 131, both raw transports initially score worse, so the same initial-score explanation does not apply. Subsequent nuisance optimization may still change that conclusion.

The original configured-reference distances are 12.624524/3.331478/0.794920 km for 109 (full/low/high), and 8.158713/2.562646/0.674606 km for 131. DS22's reference remains unconfirmed. These distances identified diagnostic examples only. All transported vectors preserve their saved source geography; no reference-informed seed or ranking is used.

Qualification uses the existing exact native half/full transport port. It verifies source score, masked full-model score, physical-gradient pullback, window and native branch identities, posterior/clutter probabilities, correction values, and orbit predictions. The original 36/39-satellite banks remain unchanged. Maximum correction discrepancy is 1.17e-10 Hz; masked objective discrepancy is at most 3.28e-11; gradient pullback discrepancy is at most 5.46e-9. Raw target states are feasible without initializer projection. All four source-half endpoints are interior to their own 25 km disks, so the boundary screen did not trigger extra derivative probes.

Actual work: 14 objective evaluations and eight additional explicit orbit predictions, zero optimizer calls, 27.08/29.96 seconds including source checks. Each process was externally bounded by 135-second TERM/140-second KILL and a 120-second internal completion deadline. Sources/tests are frozen under commit `6d422ea13`; eight qualification/transport/diagnostic tests pass with the repository's analysis-test import path, and Ruff passes. Initial test collection attempts lacked that import path; no scientific input changed to resolve it.

The next control is six single-invocation full-band continuations: original full, transported low, and transported high for each case. Each receives the same 60-second total bound, five-second independent-audit reserve, and 600 iterations, with actual objective calls recorded. There is no restart, diagonal scaling, new candidate, or larger disk. Each retains its source 25 km disk and the global prior. The original accepted full estimate remains eligible; only strictly accepted new endpoints can replace it by training objective. Both three-call matrices must seal before a fresh position comparison. This adds search budget and does not alter the published cohort curves.

Qualification receipts: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-contained-fusion-qualification-v1/{DS22-109,DS22-131}`. Continuation driver: `tools/ds22_contained_fusion_control.py`, commit `923e08f56`.
