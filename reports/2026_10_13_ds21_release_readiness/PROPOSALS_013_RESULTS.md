# DS21-013 fitted-only initialization

DS21-013 completed all six initialization stages and exported six physical
proposals per channel view. The final shared bank contains 49 satellites. This
extends development initialization coverage to nine of 34 recordings; it does
not establish final position accuracy. No reference or held observations were used.

| Stage | Completed work | Stationary fits | Elapsed seconds |
| --- | --- | ---: | ---: |
| Discovery | 100 geographical points; 300 per-view fits | 298 / 300 | 368.056 |
| Doppler shape | Three starts in each view | 9 / 9 | 22.055 |
| Fresh bootstrap | Nine calls; all complete | — | 27.303 |
| Absolute-frequency hybrid | Nine fits at shape proposals | 9 / 9 | 41.105 |
| Cold bootstrap | Nine calls; all complete | — | 30.578 |
| Six-proposal export | 18 physical exports; zero optimizer calls | — | 28.106 |

Each stage ran in a separate bounded slice; the two nonstationary discovery fits
remain in the receipts and were not retried. Timings include stage preparation
and exclude separate freeze commands. The causal catalogue contained 11,129
Starlinks; the regional bank retained 1,052, built in 4.403 seconds. Discovery
selected a 42-satellite union; fresh bootstrap expanded it to 49, retained by
cold bootstrap.

The original training selector's three geographical proposals are preserved.
They are widely separated, as are the low/high shape solutions; no reference
ranking or reference-driven search expansion was used. This ambiguity must
remain visible in the subsequent model comparison.

Exports preserve `cold-0`, `cold-1`, `cold-2`, `shape-low`, `shape-high`,
`shape-all` in each view. Maximum source-function closure error is 7.276e-12 Hz
for CH1–8 and zero for both halves. These views share discovery and physical
proposal information, so they are not independent end-to-end half-band pipelines.
All new arms use fitted c; the shape stage's removal of RF-constant offsets is
not evidence that it learns the RF calibration coefficient. Hybrid coefficients
remain diagnostics rather than replacements for the declared bootstrap seeds.

The unchanged generic initializer is commit `7928ec683`, binding 402 source files
including the native binary and C++ source. Every stage's completion, source,
parent and artifact checks passed, followed by a final recursive validation.
Compact hashes, counts, selected proposals and closure measurements are in
[PROPOSALS_013_RESULTS.json](PROPOSALS_013_RESULTS.json).

Twenty-five fast development recordings still require initialization. DS21-013
final A/B/C fits and evaluation have not run. DS21-009 model fitting is underway
with the separate [v2 seed-transfer correction](INITIALIZATION_009_V2_RESULTS.md).
The 20 locked fast cases remain unopened for inference. The full-DS21 0.5 km
target remains unmet.
