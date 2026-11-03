# DSX01: three parallel model implementations and evaluation

The evaluation was agreed before implementation. [Protocol](EVALUATION.md). These are bounded research fits, with strict convergence reported separately. No production settings, recordings, detections or frozen dataset memberships changed.

![Per-recording comparison](comparison.png)

| Method | Full-scan associations | Associated RMS (Hz) | Challenge associations | Regional KKT passes |
|---|---:|---:|---:|---:|
| original | 11222/20084 (55.88%) | 160.29 | 96/693 | 4/5 |
| continuation | 11230/20084 (55.92%) | 160.55 | 96/693 | 3/5 |
| A | 11880/20084 (59.15%) | 159.57 | 253/693 | 0/5 |
| B | 11222/20084 (55.88%) | 160.34 | 96/693 | 3/5 |
| C | 11223/20084 (55.88%) | 160.34 | 96/693 | 3/5 |

The original endpoints passed their saved production audits. The research KKT audit uses the common full regional search disk. In particular, S02 was stationary on its original active 25 km local disk; removing that disk makes its regional KKT fail. This does not invalidate its published production receipt. Every variant and continuation uses the same regional domain for this comparison.

| Source | Recording |
|---|---|
| S01 | fast8-auto-20261016-161535-99008d35-1-lower |
| S02 | fast8-auto-20261016-210123-05c5faad-1-upper |
| S03 | fast8-auto-20261016-213139-8bb8d5d7-1-lower |
| S04 | fast8-auto-20261016-220156-22c968b0-1-upper |
| S05 | fast8-auto-20261016-223211-029a4eef-1-lower |

Original → A, fitted-c. Timing differences use the same ordered satellite bank; RMS Δτ is the change in total satellite timings, not frequency residual RMS.

| Source | Association (%) | Associated RMS (Hz) | Common τ (s) | RMS Δτ (s) | Configured-reference distance (km) |
|---|---:|---:|---:|---:|---:|
| S01 | 34.25 → 37.84 | 164.87 → 165.58 | -1.594 → -1.312 | 2.192 | 132.176 → 132.024 |
| S02 | 47.02 → 49.06 | 169.59 → 169.23 | -0.647 → -1.261 | 3.187 | 133.791 → 133.189 |
| S03 | 77.51 → 84.25 | 142.57 → 141.35 | 1.901 → 1.966 | 3.110 | 5.239 → 5.213 |
| S04 | 64.02 → 64.91 | 159.83 → 157.88 | 3.870 → 3.673 | 1.269 | 258.656 → 258.616 |
| S05 | 60.40 → 63.17 | 171.84 → 172.14 | 0.463 → 0.288 | 0.961 | 7.442 → 7.508 |

A uses automatic carrier arcs to propose shared satellite timings, then q and joint refitting. B combines evidence through a shared latent identity over disjoint carrier segments, with point clutter. C divides the same allowance across six deterministic geometry/calibration/timing starts. The original production association rule is used to measure every method.

![Residual and position-reference distributions](distributions.png)

The associated-point RMS changes population when new detections are assigned. [comparison.csv](comparison.csv) includes paired RMS on the intersection, new/lost assignments, outside-window effects, timing and reference-position distances. [satellite-timing.csv](satellite-timing.csv) has every satellite timing change; [regions.csv](regions.csv) retains all 15 frozen windows. [controls.csv](controls.csv) reports original-observation auxiliary controls C05 and C07 without adding them to the primary denominator.

The configured reference is bound by matching radio serial and validity interval to `gauss-r20-lt3d-004b-20261001-v1`. Coordinates were previously operator supplied; survey uncertainty and altitude are unknown. They are never optimizer inputs. Position distance here is distance to that configuration, not independent surveyed error.

A adds 658 net scan associations and 157 net challenge-window associations. However, paired intersection RMS worsens slightly on S01 and S05. S01 alone loses 188 previously assigned observations outside the challenge windows while adding 298 there. These losses are not hidden by the net gain. All five A endpoints fail the regional stationarity check. No method has established a material localization improvement or passed promotion gates.

Full-data warm-start experiments are development diagnostics. Temporal experiments use neutral seeds and zero frozen band contrast, excluding held CFO from fitting. Their candidate bank is still conditioned on full-recording discovery. Neither experiment is an untouched end-to-end test. Failed and nonstationary results remain in the artifacts.

![Excluded-data residual distributions](temporal-distributions.png)

| Fitted-c temporal direction | Method | Held associations | Associated held RMS (Hz) |
|---|---|---:|---:|
| early_to_late | continuation | 1202/10041 (11.97%) | 200.11 |
| early_to_late | A | 1230/10041 (12.25%) | 198.00 |
| early_to_late | B | 1228/10041 (12.23%) | 200.06 |
| early_to_late | C | 1269/10041 (12.64%) | 197.10 |
| late_to_early | continuation | 1183/10043 (11.78%) | 200.74 |
| late_to_early | A | 1227/10043 (12.22%) | 197.76 |
| late_to_early | B | 1210/10043 (12.05%) | 196.18 |
| late_to_early | C | 1145/10043 (11.40%) | 202.15 |

The neutral cold starts associate only about 12% of held observations. A modestly improves both temporal directions relative to the same-start continuation, but none of these cold training endpoints passes strict convergence. This is evidence of an unresolved initialization/generalization problem, not validation of the full-data association gains. The small residual among assigned held points must be read together with this low coverage.

Fitted-c is the headline. The complete matched c=0 sensitivity appears in [comparison.csv](comparison.csv) and [temporal-comparison.csv](temporal-comparison.csv). In the full-data runs, continuation/A associate 46.94%/47.66% with c=0, versus 55.92%/59.15% with fitted-c; these capped c=0 fits are nonstationary, so the comparison is a budget-matched sensitivity rather than a comparison of converged optima. Frequency gains do not establish geographic accuracy.

Detailed next-step diagnoses: [A](model_a_diagnosis.md), [B](model_b_diagnosis.md), [C](model_c_diagnosis.md).

The main A regression mechanism is prediction changes: 261 of 271 outside-window losses persist when the old detection probabilities are restored. In S01, retiming satellite 51117 from −14.55 s to −1.18 s replaces its earlier support. This is not explained by detection-q suppression alone. The old identities are not truth, so these are losses of established model support rather than proven new identity errors. B improves its trajectory surrogate but four of five proposals worsen the exact common objective. C exhausts its 30-evaluation allocation on all 25 alternate starts without convergence. The next iteration should preserve competing timing branches, rank them with exact predictions, and allocate refinement to fewer promising basins before changing the physical model.

Reproduce with the pinned scientific runtime documented in [RUNTIME.md](RUNTIME.md). [validation.json](validation.json) checks all 125 receipts, bounds, budgets, frozen denominators, original replay and complementary held masks.

Saved results: 125 completed receipts; 0 failures. A completed receipt means evaluation finished, not that its endpoint passed strict convergence.
