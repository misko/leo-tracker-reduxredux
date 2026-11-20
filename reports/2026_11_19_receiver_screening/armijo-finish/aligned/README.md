# Reusable ordered-phase Armijo finish

The standard `v5_armijo_aligned_finish` variant returned both fixes on all four retrospective recordings. DS26-0066 reproduced the separate phase-slot diagnostic exactly and finished 42.77 m and 34.91 m from the original no-repair v5 endpoints. The other three matched their successful unaligned endpoints, residual decisions and reassociation decisions exactly. All four met the locked regression checks. The original failed DS26-0066 attempt remains in the unaligned series. [Comparison scores](scores.csv) · [Regression checks](retrospective-gates.json) · [Sealed predictions and controls](prediction-lock.json)

## Ordered identity check

The public `run(case, work_dir)` uses the normal bound v5 case with original native factors, causal TLE and the fixed 25 km roof search region. The aligned worker supplies the residual-addition and reassociation callbacks, then delegates to the existing Armijo compact finish. Its in-memory guard accepts the existing state unchanged when the phase initializer already has one entry per catalogue row. When the vector is short, the guard verifies that the observed residual addition appended one new identity to the exact ordered prefix and that all old seed labels still resolve. It supplies only that slot's zero-second initializer, as used for new slots by frozen v5.

The worker imports the same pure `prepare_remap` function as the independently sealed phase-slot diagnostic. That function operates on the live context and observed identities. The reusable path has no case predicate and opens no diagnostic receipt or report. The qualification runner separately binds the code and retrospective roster. Prior phase means, per-arm references and frozen decision logic are unchanged. Each aligned worker received the exact same scientific request as the first attempt after excluding the output-directory field. [Source binding](source-lock.json) · [Matched numerical requests](matched-requests.json) · [Separate diagnostic arrays and traceback](../phase-retry-prediction-lock.json)

## Position and runtime

Paired values give `c = 0` followed by fitted `c`. Each replay started from archived capture-era detections, rebuilt tracks and ran the complete compact finish on one CPU. Wall and CPU include worker launch and result handoff. Peak RSS reports the largest waited process. Concurrent qualification used CPUs 0, 2, 3 and 6. These runs establish retrospective regression behaviour on known cases. [Protocol](PROTOCOL.md) · [Full worker receipts](positions.jsonl.gz)

| Recording | Position error (km) | Shift from unaligned (m) | Wall / CPU (s) | Peak RSS (KiB) |
|---|---:|---:|---:|---:|
| DS26-0066 | 1.209 / 1.191 | Primary failed | 183.70 / 176.42 | 1,806,804 |
| DS26-0287 | 0.502 / 0.439 | 0 / 0 | 119.17 / 115.66 | 1,736,216 |
| DS26-0002 | 0.561 / 0.578 | 0 / 0 | 119.40 / 117.41 | 1,782,168 |
| DS29-0082 | 0.567 / 0.516 | 0 / 0 | 90.49 / 86.57 | 1,307,828 |

DS26-0066 exercised one repair at index 1375 for the adopted NORAD 66468. It adopted 67 observations in each arm and selected `62025_to_68047`. Its conditional RMS was 69.872 / 69.940 Hz. The other three had no reassociation remap to align. Unit tests separately exercise an equal-length remap with no diagnostic archive, a valid single append with arbitrary identities and a rejected reordered prefix. [Primary results and original v5 references](../README.md) · [Runnable benchmark variant](../../../../tools/pipeline_eval/README.md)
