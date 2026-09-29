# Endpoint interpolation prototype

This research-only runner performs frozen boundary-fallback full searches on
the first and last 20 ms windows of each 120 ms dual-receiver dwell. It then
associates all endpoint candidates and runs the actual 16-frame current-IQ
GLRT at local timing seeds for the nine middle windows.

Build and invoke it as:

```sh
python3 build.py --output builds/host-v2
python3 build.py --output builds/arm-v2 --arm
builds/host-v2/endpoint_probe RATE EXACT_C128 CONTROL_C128 DUAL_CI16 MODE
```

`MODE` is `pairs-only`, `union`, or `union-fallback`. Templates contain one
native `leo_presence_complex` frame (two FP64 values per complex sample), and
the CI16 file is exactly 120 ms of sample-major, receiver-major interleaved IQ.
The output is exactly 22 JSONL rows in `(window, receiver)` order.

Association is deterministic cardinality-first minimum-cost one-to-one matching
over at most 8 by 8 endpoints. An edge requires circular timing distance at
most 8 samples and tracking-CFO distance at most 8 kHz. Timing phase uses exact
turns `epoch * 750 / rate`; it never accumulates a rounded integer frame size.
The first endpoint is the unwrap anchor and the last endpoint is placed at its
nearest frame alias. Paired timing and tracking CFO are linearly interpolated.
`union` also retains each unmatched endpoint as a constant nearest-endpoint
hypothesis. All endpoint candidates, including negative-margin candidates and
duplicate aliases, participate. Each seed evaluates rounded timing and its
two adjacent samples, retaining the highest-margin actual GLRT result.
Predicted tracking CFO is clamped to the public GLRT acquisition interval
[-400, 400] kHz for the actual call while the unclamped prediction remains in
metadata. `union-fallback` runs the frozen blind search when no local result
meets the 0.025 margin gate.

Endpoint discovery occurs in physical order (window 0, then window 10), only
after the complete dwell is present. No middle computation begins until both
endpoint searches finish. Non-run full-search candidate fields are JSON null
and explicitly described by `fields_valid`; predicted tracking CFO is passed
as `acquired_cfo_hz`, while `tracking_cfo_hz` includes the actual GLRT residual.
