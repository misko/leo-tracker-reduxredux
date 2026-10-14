# A conditional half incumbent replay

All earlier accepted half endpoints remain eligible. The old and fresh half objectives and domains are identical; changing the full-state initializer does not invalidate an accepted half fit. This corrects the earlier implication that only fresh half calls should be used with the repaired full selector.

The current PD full selector and the training-selected pool of **all old and fresh** conditional half endpoints give:

| Case | Full CH1–8 km | Conditional CH1–4 km | Conditional CH5–8 km |
| --- | ---: | ---: | ---: |
| DS21-035 | 7.223109 | 7.101238 | 7.495502 |
| DS21-053 | 1.343357 | 0.190263 | 1.444907 |

These are conditional views with the full-derived fixed learned shifts, candidate bank, frame, priors and original disk. They are not independently trained half-only A pipelines. The full result exceeds the low-view error in both cases. There is no full-cohort promotion or target-achievement claim.

The source-frozen audit executed 16 objective evaluations and zero optimizers in 15.336 seconds. It replayed every one of eight old/fresh endpoints, including rejected endpoints. Complete semantic input hashes agree for observations, candidate bank, prior, likelihood settings, masks, q basis/precision, clock design/nodes/null/precision, calibration design/baseline/frame, timing basis, nuisance limits/scales and original solver/domain options. Objective, NLL, physical and nuisance gradients and association posteriors agree exactly (maximum discrepancy zero) at every endpoint. Original strict KKT and accepted/rejected classifications also replay.

Training selection chooses fresh endpoints for both 035 views and 053 high, and the previous accepted endpoint for 053 low. Selection used only the own half objective. The fresh 053-low outcome has lower objective (12871.457168 versus 13086.953686) but KKT 0.898129, so it remains rejected. This is an unresolved convergence/search gap, not evidence that the accepted low incumbent is globally optimal. The earlier accepted endpoint is retained because it requalifies, not because its configured error is small.

The full q035/q053 numerical repair remains current: 7.223109/1.343357 km. In particular, the historical q053 0.256462 km full result lost training selection once previously rejected lower-objective states became eligible. Its earlier randomized CV penalty (+377.047 opposite-fold NLL versus conditional uniform weighting) remains a warning about generalization. The restored 0.190263 km low incumbent does not change that full-model conclusion.

Protocol source: `90bec4743`. Four component tests and Ruff passed. Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-half-incumbent-replay-035053-v1`. Scientific seal: `2f08bf65e5d10f0105bebef9277e4042a33f3099f75d4d8db25d8744160ef7ab`. All replay outcomes and selectors sealed before configured-reference evaluation; evaluation used zero objectives and took 10.054 seconds. No original outcome or failure was overwritten.
