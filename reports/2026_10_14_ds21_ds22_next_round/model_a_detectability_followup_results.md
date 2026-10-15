# A029 boundary and A071 genuine B source: zero-fit follow-up

The source-frozen audit completed 15 objective evaluations and 7 explicit geometry calls in 2.947 s, with zero fits or reference accesses. It separates an active local constraint in 029 from omitted genuine calibration/basin state in 071. Source `e661a2b5d`; four owned tests and Ruff passed.

## 029: genuine local descent, not monotonic descent over 100 m

The accepted contrast path 5 is at radius 25.000000000086 km in its own 25 km disk. Its global prior still has 170.723 km radial slack. Its outward derivative is **−17.088717 J/km**; the tangential gradient is approximately [−9.62e−6, 5.19e−6].

| Radial step | Central FD, J/km | Forward FD, J/km | Outward ΔJ |
|---|---:|---:|---:|
| 1 m | −17.088738 | −13.128922 | −0.013129 |
| 10 m | −17.090787 | +22.506762 | +0.225068 |
| 100 m | −17.258091 | +378.139752 | +37.813975 |

All probes remain feasible under the original global prior; outward probes leave the original local disk. No hard visibility, soft support, or interpolation-cell memberships change at either side of any step. Central differences confirm the analytic derivative, while the forward differences show strong positive curvature. The original prespecified **all-forward-descent gate failed** and remains failed. This does not negate the verified feasible 1 m decrease.

A proposed new matched control repeats the same complete state in the original 25 km disk and a local disk of radius **305.585293 km at the same center**. The latter covers the entire original 250 km prior disk by the triangle inequality; `_Problem` retains the original global disk and all other bounds. Both calls would receive 60 s, 6,000 actual objective evaluations including one reserved independent audit, and 600 iterations. The amended trigger explicitly uses analytic/1 m central agreement, feasible 1 m decrease, and unchanged support; it does not rewrite the original gate. No such fit is included here.

The original endpoint is strict only under its original local constraint. Under the proposed wider domain its physical KKT is 15.037671: it is a feasible historical source, not a strict widened-domain incumbent.

## 071: omitted genuine complete calibration/basin state

The saved B training winner is original path 1, with its own [-87.5, −87.5] km center and 25 km disk. Its receiver high-minus-low offsets are [−19812.197081, 39948.908621] Hz. None of the six frozen A contrasts represents that complete correction: even after the correct common-intercept rebase, remaining row RMS differences are 536–3623 Hz.

Retaining B's own offsets as a seventh fixed-contrast source path closes exactly. The inverse transport is `a_raw = a_centered − f_high * delta_B`; common clock, slopes, fitted c, satellite timings, and source geography remain unchanged. Maximum row correction error is 1.46e−11 Hz, vector round-trip error 9.09e−13, and objective/NLL error at most 7.28e−12. The 50 kHz offset prior is retained exactly once (0.397688); common intercepts have no prior. No alias adjustment or initializer projection occurs, and the untouched source is feasible in its own disk.

| q family | B-source zero-q J | Current accepted A-source q J | B-source minus current |
|---|---:|---:|---:|
| Shared | 31877.835354 | 32339.537682 | −461.702328 |
| Contrast | 31877.835354 | 32138.752903 | −260.917549 |

Raw/frozen versus centered/joint representations also close for both q densities: objective error ≤3.64e−12, physical gradient error ≤1.27e−10, q gradient error ≤1.14e−13, and posterior error ≤1.02e−13. This tests the representation at identical source functions; it does not release offsets during a fit.

The zero-q source is already lower-J than both accepted selectors, but is **not a q incumbent**: its scaled q gradients are 144.873 and 99.340. The evidence supports adding the genuine state to the initializer inventory rather than claiming the current search optimized this family. The source was chosen by saved B training selection, not by configured position. Proposed next control: B source versus current A-q complete source, both shared and contrast, four matched 20 s / 2,000 actual / 600-iteration calls; retain all historical strict q endpoints. This is explicit extra search cost. A consistent future cohort recipe must add the B path prospectively, not only for 071.

Actual authority: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-detectability-followup-029071-v1`. The adjacent JSON binds protocol, launch, result, seal and termination bytes and preserves the full finite audit inventory. No optimizer ran in this diagnostic, and no original cohort output was replaced.
