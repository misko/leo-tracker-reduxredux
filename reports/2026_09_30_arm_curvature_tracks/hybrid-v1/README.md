# Native-coarse-seeded curvature tracker research

This bounded follow-up replaces the expensive adjacent-pair initializer from
`../research-v2` with tracks produced by the existing native 151-slope-bin,
8-peak, 512-intercept-bin, minimum-8-point/4-second, cap-16 coarse tracker.
The seed tracks are source-only results from the same candidate input. They do
not contain server labels, TLEs, or oracle identities.

Each coarse seed is validated against the original input: exact candidate ID,
lane, one candidate per source group, alias-consistent dealiased CFO, and the
same minimum support/span policy. The seed's observed members initialize local
frequency/rate/curvature state at its center. The tracker then traces in both
directions and reassociates every other original source group. Association and
curvature behavior are unchanged from research v2.

The default output is an expanded hypothesis bank. `--retain-originals` adds
the exact coarse memberships as explicit alternatives so extension cannot hide
a useful coarse result. This can deliberately produce overlapping hypotheses;
the output is labeled `hypothesis-bank:no-exclusive-assignment`. There is no
final one-observation/one-track assignment in this research component.

On the frozen ARM-observation input, 94 native coarse seeds produced 62
expanded tracks with 117,381 state evaluations in 0.0491 host seconds. Retained
mode produced 156 hypotheses: 94 exact originals plus 62 expanded hypotheses.
On the corresponding server-observation input, 101 independently generated
native coarse seeds produced 62 expanded tracks with 106,254 state evaluations
in 0.0499 host seconds. These are execution and shape facts; correctness and
server/ARM membership plots are owned by the parent evaluation and are not
inferred from equal counts.

The component test adds invalid seed membership and genuine curved/gapped
extension checks to the v2 curved, alias, crossing, miss, noise, gap, runaway,
and source-time validation suite. Host and ASAN/UBSAN runs pass. ARM binaries
are cross-built but not physically run in this component receipt.

`host/arm-a250.*` preserves the first rejected CLI attempt, which failed before
reconstruction because an unsigned track-index parser treated index zero as
out of range. The corrected, source-bound results have the `-v2` suffix.

Example:

```sh
reports/2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks \
  reports/2026_09_30_arm_fast_tracks/server-baseline/output/arm-observations.tsv \
  --acceleration 250 \
  --seeds reports/2026_09_30_arm_curvature_tracks/hybrid-v1/seeds/arm.tsv \
  > arm-expanded.tsv

reports/2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks \
  reports/2026_09_30_arm_fast_tracks/server-baseline/output/arm-observations.tsv \
  --acceleration 250 \
  --seeds reports/2026_09_30_arm_curvature_tracks/hybrid-v1/seeds/arm.tsv \
  --retain-originals \
  > arm-retained-bank.tsv
```

The full local-pair primary remains frozen in `../research-v2`; this directory
does not reinterpret or overwrite its negative ARM runtime result.
