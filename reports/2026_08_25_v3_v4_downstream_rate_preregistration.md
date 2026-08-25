# V3/V4 acquisition-yield and downstream-rate preregistration

Date: 2026-08-25

## Status

This protocol was committed before this experiment opened any new raw-IQ
response or computed any new downstream odd-Qin error.  It is bound to the
single, already opened POST-FIX canary
`cap-20260825T150802-473cb5bbcbd6`.  Every `holdout_foundation` capture, every
newer capture, every dynamically discovered capture, and every substitution is
forbidden by the [dataset policy](2026_08_25_doppler_experiment_dataset_policy.md).
The closed machine-readable protocol is
[`v3-v4-downstream-rate-benchmark-v1.json`](../config/analysis/v3-v4-downstream-rate-benchmark-v1.json).

## Questions and frozen populations

The benchmark keeps three questions distinct:

1. **Acquisition/yield:** validate and summarize all 537 hypotheses in the
   existing digest-bound full-canary scientific receipt.  No success or failure
   may disappear.
2. **Both-method common mode:** compare downstream future odd-Qin prediction
   only where V3 and V4 both acquire the same frozen anchor and both provide the
   same even-selected target ordinal.
3. **One-method-only windows:** report V4-only recovery and V3-only regressions
   separately.  Missing errors are never imputed and never folded into the
   paired comparison.

The downstream subset is not selected from V3/V4 outcomes.  Before IQ is read,
the protocol freezes one row per each of the 20 source branches: the earliest
`(source_probe_sample_start, row_key)` in the already committed 537-row input.
All 20 exact row keys, source branches, streams, receivers, start samples, and
row-input digests are embedded in the config.

## Downstream measurement and causal test

For each acquired anchor, the experiment projects the acquired frame epoch on
the exact 750 Hz `3333/3334` sample lattice for one second.  The frozen upstream
local rate is used only as the per-frame demodulation NCO origin, keeping the
residual search inside its fixed ±2 kHz basin.  The public split-frame kernel
then estimates CFO independently on even and odd Qin symbols.

Only even Qin can admit a frame or fit a rate.  Its frozen gates are exact
coherence at least 0.02, exact-minus-roll-control margin at least zero, and no
residual-grid boundary.  Odd Qin is retained solely as the future response.
An odd value, odd residual, or odd likelihood cannot select an anchor, frame,
target, history, or fit.

At each predeclared target offset from 625 through 975 ms, the rate fit stops
125 ms before the target.  A deterministic Huber degree-one line uses either
the trailing 20 ms or trailing 500 ms of past even-Qin CFO.  The primary strong
baseline is fixed 500 ms and requires at least 300 frames spanning at least
450 ms; fixed 20 ms is retained only as context.  Predictions are scored on
the target frame's odd-Qin CFO.  The common-mode mask is the intersection of
the two methods' even-only masks at the same target ordinal.

## Frozen interpretation

The benchmark is adequately supported only with at least eight common anchors
and 40 paired fixed-500-ms predictions.  V4 is acquisition-useful only if its
all-population numerical yield is not below V3 and its common-mode fixed-500-ms
odd-Qin RMS is no worse than 1.05 times V3.  A ratio at or below 0.95 is the
predeclared threshold for a material common-mode improvement.  Results between
0.95 and 1.05 are parity/noninferiority, not a tracking advance.

This is an opened-canary implementation regression, not untouched holdout
evidence and not a Standard promotion test.  V4 changes acquisition and then
delegates to a fresh instance of the unchanged V3 continuous tracker.  The
comparison therefore asks whether V4 finds more usable windows without
degrading downstream rate geometry; it does not call V4 a new tracker.

Finally, the frozen Standard source/epoch/trajectory products and V3/V4
acquisition have seen wider evidence, including odd Qin in parts of their
conditioning.  The odd lane is held out from the downstream line only, not
from upstream source selection or acquisition.  The response measures
receiver-relative CFO prediction consistency, not absolute Doppler truth;
LNB and receiver-clock drift remain outside this experiment.
