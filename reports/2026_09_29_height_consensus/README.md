# Cross-dataset agreement can conceal height-induced position shifts

**The tested height effect is mostly shared across datasets, so location agreement cannot independently calibrate height or certify accuracy.** At +100 m height, the N24 estimates' centroid moves 169 m while their RMS spread improves by only 4.9 m. At +300 m, the centroid moves 556 m while RMS spread increases by 49 m.

This decomposes the actual saved [N8](../2026_09_29_height_sensitivity/README.md) and [N24](../2026_09_29_height_n24/README.md) fits. No operator reference coordinate enters the calculation and no additional radio optimization is run.

| Panel | Fixed height | RMS spread between dataset estimates | Centroid movement from zero-height result | Shared fraction of squared movement |
|---|---:|---:|---:|---:|
| N8 | 0 m | 857 m | 0 m | — |
| N8 | 100 m | 875 m | 197 m | 77.1% |
| N8 | 300 m | 913 m | 578 m | 73.5% |
| N24 | 0 m | 224 m | 0 m | — |
| N24 | 100 m | 219 m | 169 m | 90.0% |
| N24 | 300 m | 273 m | 556 m | 88.0% |

Each row uses three estimates, one each from DS7/DS8/DS9. RMS spread is distance from the equally weighted centroid, not error from true position. The centroid movement is sensitivity to assumed height, not measured bias. The shared fraction is a deterministic decomposition of squared shifts, not a probability, confidence level or variance estimate from repeated independent trials.

Among the three tested heights, minimum N24 spread occurs at 100 m, whereas minimum N8 spread occurs at zero. No tested positive height reconciles the N8 discrepancy. This is not an estimate of actual antenna height: only three fixed heights were tested, N8 is nested within N24, and the fits share model assumptions and site-conditioned banks.

## Calculation

Use the optimizer's common east/north kilometre coordinates. The script verifies that the N8 and N24 manifests use the same geographic origin. For dataset d, define displacement `delta_d = position_d(height) - position_d(0)`. Decompose it into the mean displacement and a residual specific to each dataset:

`mean(||delta_d||²) = ||mean(delta_d)||² + mean(||delta_d - mean(delta_d)||²)`.

The shared fraction is the first term divided by the left side. It is null at zero height where all displacements are zero. Pairwise dataset distances are retained in `results.json`. These planar E/N diagnostics intentionally use the fitted coordinate system rather than introducing a new geodesic approximation into the decomposition.

## Consequence for the subkm effort

The height question cannot be settled by choosing whichever value makes the three datasets agree most closely. A shared geometric error can shift all three estimates together, leaving agreement nearly unchanged. Independent antenna elevation/datum remains necessary for a defensible physical correction. This result strengthens the distinction between repeatability and absolute accuracy without assuming which tested height is true.

Preserve the baseline and the fixed-height sensitivity evidence. Once independently supported elevation is available, apply it consistently and compare both location and held prediction. Do not add a height chosen from this scatter comparison or interpret the 219 m N24 spread as a calibrated horizontal error bar. Reference uncertainty and shared orbit/association assumptions remain separate unresolved issues.

## Validation and reproduction

Three tests pass: a common translation leaves scatter unchanged; opposite displacements isolate the differential component; invalid point-set membership is rejected. The variance decomposition identity is checked for every result. Source fit qualification, input hashes, tested heights and common coordinate origin all verify. An initial output is preserved as `initial-results.json`; a subsequent replay added the explicit common-origin assertion and updated code bindings, with numerical results unchanged.

```sh
python3 -m unittest discover -s reports/2026_09_29_height_consensus -p 'test_*.py'
python3 reports/2026_09_29_height_consensus/build.py
```

The writer creates `results.json` exclusively; replay in a fresh output context. Results, source hashes and `evidence.sha256` are local. No RF, archive export, production change or remote publication occurred. Reliable absolute subkm accuracy remains unverified.
