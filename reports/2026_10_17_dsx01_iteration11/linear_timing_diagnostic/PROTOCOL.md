# Frozen linear-timing diagnostic, before any target calculation

This is a bounded diagnostic of the proposed per-point linear timing working
model, not a likelihood fit, true-orbit Gaussian marginal, physical accuracy
test or recovery result. It uses no measured CFO, held response, reference
coordinates, manual window, emitter labels or selected satellite insertion.

Use agent A's sealed iteration11 unsupported-prediction producer and both OLD
iteration9 prediction arms. Require the immutable fitted-c and c0 terminal
states, original complete calibration, the original selected45 IDs and the same
causal metadata845 bank (800 unsupported IDs). Verify both prediction seals and
source hashes before numerical checks. No full source/model preparation,
selected-model objective replay, propagation, optimization or density scoring
is permitted. Only the sealed blank metadata NPZ, saved complete states and
metadata-only bank/context ports may be read.

Choose rows before calling any orbit function. Eligible rows are TRAIN only.
Within each `(receiver, channel, actual_RF_hz)` lane, order unique global
observation IDs by SHA256 of `linear-timing-metadata-v1\0` followed by the UTF-8
ID, with the ID as the tie-break. Retain at most two per lane. If more than32
rows remain, retain the32 smallest hashes across lanes. The same selected IDs
must occur in both RF arms. Do not change membership after errors are observed.

For every selected row and all800 unsupported candidates, evaluate exact public
orbital frequency predictions and soft visibility at

```
delta_seconds = [-6, -4, -2, -1, 0, 1, 2, 4, 6]
satellite_total_timing = saved_OLD_common_timing + delta_seconds
```

Compare with the sealed producer's `mu + g * delta` and its delta-zero
visibility. Preserve its complete learned correction, actual RF, bank identity
and interpolation rules. No unsupported independent timing or q coordinate is
fitted. The OLD fitted-c and OLD c0 states are already separately trained
controls; this diagnostic does not reinterpret them as whole-pipeline c0.

The ledger permits exactly one `predict_orbits` and one `elevation_geometry`
call per arm/delta: at most18 of each, including both delta-zero checks, plus18
algebraic soft-horizon transforms of those returned elevations. No
extra baseline, derivative stencil, retry, alternative delta or replacement row
is permitted. The orbit call may return its native first timing derivative but
no additional derivative evaluation is allowed. Launch externally bounded at
60s TERM/65s KILL with the pinned single-thread runtime. Reuse the existing bank;
there are zero new propagation, objective, likelihood and optimization calls.

Freeze this protocol, component tests, runner source and every input binding
before the first call. Persist an inventory with chosen IDs, metadata, candidate
ordering and call allowance. Retain every declared outcome/failure without
automatic retries; save raw exact/linear frequencies, frequency errors and
exact/delta-zero visibility, not only summaries. Persist the call ledger as
calls start so an interrupted run cannot silently claim zero cost.

Errors are the unwrapped physical prediction difference `exact - linear`,
without measured CFO, alias wrapping or best-candidate selection. For each arm
and delta report signed error quantiles, absolute error quantiles
(0,50,90,95,99,100 percent), RMS/max error, and visibility changes/crossings.
Crossings use the fixed public hard horizon (`sine_elevation >=0`) at delta and
zero; also retain soft weights, counts of unequal weights and maximum absolute
weight change. Report delta-zero frequency/visibility closure explicitly.
These are descriptive errors. No physical accept/reject threshold, source
selection, dropped candidate, changed population width or held-data model choice
will be derived from them.

Owned synthetic tests must verify hash selection under metadata permutation,
TRAIN and lane caps, no measured-response/reference access, original ID
preservation, exact accounting of delta-zero calls, refusal of excess calls,
and error/visibility summaries. These tests use fake ports only. The actual
bounded diagnostic may run only after the two producer seals are available and
verified. No held evaluation or model campaign is authorized here.
