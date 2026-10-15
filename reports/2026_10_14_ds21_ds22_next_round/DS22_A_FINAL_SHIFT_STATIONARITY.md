# A059/A105: learned band shifts cease to be stationary after the final fit

All eight completed method/scope selectors have a feasible downhill direction in their frozen high-minus-low receiver shifts. The original final fits are stationary only subject to holding those shifts fixed. This is expected under the sequential architecture, not a faulty original KKT certificate. It supplies a concrete reason to test releasing the shift constraint under one joint objective, but does not establish that release will improve position or path ranking.

The high stage estimates shifts while holding the low-stage geography and common correction fixed. The final stage then moves geography, common calibration and satellite timing while holding those shifts exactly fixed. The derivative audit asks whether the same offsets would remain stationary at that changed final state. It uses the original high-offset prior once, not a learned posterior added as another prior.

| Case / final timing / scope | RX0 derivative per Hz | RX1 derivative per Hz |
|---|---:|---:|
| 059 / high / original six | 0.679638 | 0.041331 |
| 059 / high / covered 22 | 0.696504 | 0.017496 |
| 059 / low / original six | 0.534622 | 0.095149 |
| 059 / low / covered 22 | 0.762831 | −0.001851 |
| 105 / high / original six | 0.049545 | −0.200101 |
| 105 / high / covered 22 | 0.049545 | −0.200101 |
| 105 / low / original six | −0.114024 | 0.102525 |
| 105 / low / covered 22 | −0.015675 | −0.072815 |

The A105 high-timing scope rows repeat the same selected endpoint; they are not independent outcomes. Derivatives include `offset/50000²`, the original Gaussian prior derivative. Receiver order is explicit in the saved scientific export. The corresponding 5000-Hz chart gradients reach 3814.15, but these are partial derivatives rather than a recomputed full constrained KKT statistic. All offsets lie inside their original ±ALIAS/2 bounds, and the ±0.1-Hz probes are feasible.

Forty actual objectives (20 per case), zero optimizer calls, reproduce every source J within 1e−6 and check both receiver derivatives by central differences. Maximum analytic/finite-difference discrepancy is 3.63e−8 per Hz. Each selector has an actually evaluated lower-score ±0.1-Hz probe; decreases range from 0.00725 to 0.07615. There is no position movement in this experiment and no reference read. Numerical scoring takes 0.386/0.401 seconds; preparation and source verification are additional work. Each process had an independent 180-second TERM/185-second KILL bound, with a 120-second internal scoring cap; both exited successfully. Two component-owned tests and Ruff pass.

The [path audit](DS22_A_COMPLETION_PATH_AUDIT.md) separately shows A059's selected low-stage geography is already far from its configured reference and the missing constant prior changes no winner. These results address different questions: correcting the small prior ledger does not fix path selection, while releasing the frozen shifts changes the inference problem itself. A matched constraint-release prototype must preserve complete initial correction functions, candidate banks, original domains, data and priors, then rank only by the declared objective. Better training score alone will remain insufficient for promotion.

Source `7c753adee`, `tools/model_a_final_shift_audit.py`. Outputs are `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-final-shift-audit-v1/{DS22-059,DS22-105}` with source snapshots, protocols and seals. Terminal SHA-256: A059 `da8bbd8f70e43c79797286ecf6a42a21a12c9dad89cf1e20af03d3614621885f`; A105 `24ec59c9103ef36a95d31a7c45ec859b4b30881046826d66b3e972fa64d88b54`. Only existing development observations were scored; no held/locked data or new collection was used. No cohort performance curve changes.
