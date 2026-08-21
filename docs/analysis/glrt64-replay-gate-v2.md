# GLRT64 replay gate V2

V2 is additive. It does not alter or reinterpret persisted
`standard.cfo-lift-replay.v1` products.

The independently optimized per-probe CFO baseline is a strong local optimizer,
so V2 does not require a smooth trajectory to beat it on half the individual
probes. Replay rows are first reduced to deterministic one-second blocks by
`sample_start`; the median of each block gives every time interval one vote,
independent of probe density.

## Tier ordering

1. Geometry below five observations, one second, or the frozen residual limits
   is `insufficient` and enters neither inventory.
2. Credible geometry with inadequate replay coverage or corrected GLRT64/control
   separation below `0.05` is `geometry_only`.
3. Strong absolute evidence with too many materially harmful blocks is
   `replay_rejected`.
4. Strong, safe evidence whose block-median gain exceeds the calibrated
   equivalence band is `replay_improved`.
5. Strong, safe evidence within the calibrated band is `replay_stable`.
6. Remaining materially degrading replays are `replay_rejected`.

Only `replay_improved` and `replay_stable` enter the automatic-correction
inventory. Every geometrically credible row, including `geometry_only` and
`replay_rejected`, remains in the separately named geometry-display inventory.

The equivalence tolerance is not an inline decision constant. It is
`safety_multiplier * p95(abs(block_delta))`, derived from the exact named
noise, zero-IQ, wrong-edge, wrong-alias, time-shift, and unrelated-IQ control
vectors embedded in the gate configuration and bound by a receipt digest.
Changing any vector or multiplier changes the gate configuration digest.

Polynomial selection also belongs to V2: when several degree 1/2/3 models are
within `2` BIC units of the best fit, V2 replays the simplest one.
