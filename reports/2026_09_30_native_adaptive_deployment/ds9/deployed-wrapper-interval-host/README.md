# Certified interval coarse-screen experiment

This research-only mode applies the deployed-server wrapper geometry and
retention rules while screening the full FP64 coarse grid with a conservative
FP32 interval calculation.  It does not use fixed-K pruning.  A row that does
not prove a complete answer within the bounded priority-frontier work budget
runs the frozen scalar FP64 coarse search.

For one real or imaginary correlation component with `n` taps, binary32 unit
roundoff `u = 2^-24`, normalized binary32 input `x`, FP64 rotated reference
`r`, and its effective binary32 value `rf`, the screen uses

```
gamma = ((4*n + 2)*u) / (1 - (4*n + 2)*u)
component_error / sqrt(Ex*Er)
    <= (norm2(r-rf) + gamma*norm2(rf)) / sqrt(Er)
       + (4*n + 2)*17*FLT_MIN / sqrt(Ex*Er)
```

The final term covers gradual underflow and ARMv7 flush-to-zero or
denormals-are-zero loss for normalized input components bounded by one and
template components bounded by 16.  Subnormal stored reference coefficients
are treated as zero in the certificate.  Nonfinite values, values outside
these public bounds, zero/underflowed energy, unsupported rounding mode, or a
nonfinite bound cause scalar fallback.  The complex magnitude bound multiplies
the component bound by `sqrt(2)`.  Contribution accumulation and score
formation add explicit binary64 rounding allowances, and every cell endpoint
is rounded outward with `nextafter`.

A cell is impossible as an exact local maximum only when its upper endpoint is
strictly below a neighbor's lower endpoint.  Possible cells enter a descending
upper-bound frontier.  Each visited cell and both neighbors are recomputed by
the frozen FP64 kernel.  Repaired peaks are restored to CFO-bin/epoch scan
order before the deployed stable score sort, which preserves tied `+/-` CFO
behavior independently of frontier order.  The frontier stops after eight
separated retained peaks exist only when every remaining possible cell's upper
bound is **strictly** below the exact score of the current eighth peak.  Equal
bounds continue.  Failure to certify falls back to the complete scalar grid.

The final host run covered 80 calls and 160 receiver rows.  The strict direct
rank comparison passed all 1,280 candidate slots, including 880 complete
fractional candidates, 400 explicitly unavailable candidates, 295 passing
margin gates, and all 32 peer-fallback rows.  It found no missing, additional,
availability, epoch, gate, or numerical-tolerance mismatch.  Comparing every
non-timing result field with the frozen scalar-wrapper output also found zero
differences.  The interval mode repaired a mean 24.0125 cells per row and used
no scalar fallback on this panel.  Host call CPU time averaged 141.95 ms; this
is not ARM or real-time evidence.

The exact aggregate and artifact hashes are in `summary.json`; detailed rank
and tolerance evidence is in `comparison.json`.  The host and ARM cross-build
receipts for the final guarded source are in
`../builds/host-deployed-wrapper-interval-v2/` and
`../builds/arm-deployed-wrapper-interval-v2/`.  The measured ARM experiment
used the immediately preceding source; its only difference is the explicit
rotated-coefficient domain guard.  Both panel templates have maximum complex
magnitudes below 2.563, so all rotated components satisfy the documented bound
of 16 and that guard is dormant for the measured inputs.  Production
capability parity remains false.

Reproduce a host schedule with:

```sh
reports/2026_09_30_native_adaptive_deployment/ds9/builds/host-deployed-wrapper-interval-v2/leo-native-adaptive-replay \
  --manifest reports/2026_09_30_native_adaptive_deployment/ds9/portable80/deployed-wrapper-schedules/lower-000.tsv \
  --thermal-path /nonexistent \
  --deployed-server-interval-fractional
```

The bounded three-call ARM timing input is
`../arm-deployed-wrapper-representative.tsv`.  On the saved-IQ device staging
used by the earlier scalar and register-four experiments, invoke the ARM replay
with `--deployed-server-interval-fractional`; no RF access is required.
