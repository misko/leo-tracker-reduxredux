# DS22-075: complete 60-second coverage results

All 44 prespecified native-C fits returned and were sealed before the configured-reference comparison. Twenty-four passed the unchanged strict stationarity gate. Adding the sixteen training-derived coarse starts did not change either model's selected solution: the no-clock model remains 78.429728 km from the configured station reference, and the common-clock model remains 80.766346 km away. DS22 station continuity remains unconfirmed; these are not verified accuracy estimates.

| Model | Eligible inventory | Strict accepted | Selected ordinal | Training objective | Training NLL | Configured distance km |
|---|---|---:|---:|---:|---:|---:|
| Native without common clock | original six | 6/6 | 2 | 39905.834144 | 39646.524659 | 78.429728 |
| Native without common clock | all twenty-two | 15/22 | 2 | 39905.834144 | 39646.524659 | 78.429728 |
| Native with common clock | original six | 1/6 | 2 | 39447.108044 | 39002.883933 | 80.766346 |
| Native with common clock | all twenty-two | 9/22 | 2 | 39447.108044 | 39002.883933 | 80.766346 |

Both arms used the fixed 87-satellite union. The original six endpoints kept their own 25 km disks; all sixteen original coarse-grid starts kept their declared 100√2 km disks. Coarse starts were included regardless of score, with no reference-derived centers or selection. All fits used fitted-c, unchanged priors and strict KKT threshold 0.001, 60 seconds and 600 iterations. The original 20-second experiment remains unchanged and unavailable.

Four exact 60-second outcomes from the matched budget probe were reused, including its failed projected coarse call. Only the forty never-attempted 60-second calls ran. Every new unit returned successfully; the six-worker bounded wave took 789.767 seconds. The complete inventory therefore contains 44 sixty-second fits, not 48. This is additional experimental search cost, not a baseline correction.

The best accepted no-clock coarse start is ordinal 21, objective 42305.974340, worse than the original-source winner by 2400.140196. The best accepted clock coarse start is ordinal 7, objective 40208.591540, worse by 761.483495. Their geography is not used for selection. The original-source winners were exactly reused from the budget probe.

Seven no-clock and thirteen clock fits remain nonstationary; all twenty reached the 60-second deadline with solver success false. The no-clock failures are ordinals 7, 10, 12, 13, 14, 16 and 17. Clock failures are 0, 1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 16 and 18. None were retried or accepted by weakening the gate. Process CPU/wall ratios range from 0.998127 to 0.999978. This excludes substantial CPU starvation during these calls, but does not exclude memory-bandwidth, CPU-frequency or other load effects.

The broader domains cover the declared prior square, while every original 25 km disk misses the configured reference. Nevertheless, finite local optimization and the remaining convergence failures prevent claiming that the full geographic likelihood has been globally searched. This result rules out improvement from the accepted states of this specific coverage experiment, not every association or calibration model. A better training score alone does not imply better localization.

Historical original C full/low/high distances were approximately 77.5869/23.4284/51.1464 km. They used a different bank and shared-discovery initialization. No matched full/half fit of these union-bank models was run, and no independent-half or sub-kilometer claim is made. Held and locked data remain untouched.

## Authority

- Source and evaluator: `23adcf2f6`; seven component tests and Ruff passed.
- Namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-full60-v1`.
- Protocol SHA256: `247c064573577bc793984310c6b6dece2c5de37591b82ddf5572c988298f6cef`.
- Terminal SHA256: `3a20d64c4a75c88848ecd97690f100528bcf7c5f2e99632cd2fb4c56616946db`.
- Seal SHA256: `b5c3e4864890141cd1801ae54e418b44500b3091f1091ff7c4d21c899583a66f`.
- Post-seal comparison: adjacent `ds22-c075-full60-comparison-v1/report.json`.
- Original partial-unit failures, explicit never-attempted-call completion, and all matched-budget outcomes remain recursively bound and preserved.
