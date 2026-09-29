# Native boundary-margin gate qualification

Both native variants preserve 11 windows, two receivers, eight candidates per
window, omit-power proposal features, radius-two proposal regions, and the
fused V4 NEON-moments-v2 / FP64-GLRT search. The only decision is whether a
residual-boundary candidate has sufficient initial `exact - control` margin to
enter the existing refinement path.

Each variant has a dedicated component binary in its host, sanitizer, and ARM
cross-build receipt. The host and ASan/UBSan binaries executed the finite
above/below, equality, `nextafter` below/above, NaN, and both infinities
cases; all nonfinite margins retain the fallback. ARM was cross-compiled only.

The full 704-dwell host audit used the frozen fused-V4 cohort as reference and
the frozen omit-power proposal rows. Native candidates exactly matched the
recorded `gated_candidate` replay transformation for all 123,904 entries.

| minimum margin | replay-skipped candidates | candidate mismatches | recovered standard hits |
| --- | ---: | ---: | ---: |
| 0.025 | 1,843 | 0 | 19,225 / 19,581 |
| 0.100 | 4,000 | 0 | 19,218 / 19,581 |

These are host recovery and equivalence results only. They make no ARM timing
claim; serialized ARM execution remains outside this qualification.
