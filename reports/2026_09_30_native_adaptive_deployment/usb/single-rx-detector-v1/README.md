# Single-receiver ordinary native detector v1

This slice adds a true one-receiver CI16 entry point around the production
ordinary native GLRT. `single_rx_glrt.h` consumes `[sample][I,Q]` signed-16
values, returns one row per probe window, and retains the production proposal,
regional search, conditioning, verification, fractional extension, and
eight-candidate budget. It does not allocate or analyze a second receiver.
Peer recovery is explicitly unavailable and no absent receiver is duplicated.
The published dual-receiver ABI and outputs remain unchanged.

The public API uses a distinct opaque type, capability structure, layout query,
and create/analyze/destroy symbols. Passing a live single handle to the dual API
or a dual handle to the single API fails as invalid. A context owns its plans,
workspaces, and caches, permits one operation at a time, and returns BUSY for
same-context contention. The input pointer contains native `int16_t` values;
endianness belongs to the file or transport decoder outside this API.

## Qualification

The qualification record is `qualification.json`. Its principal evidence is:

- The focused fold test compares 8,000 scalar and 8,000 Cortex-A9 NEON cases
  bitwise against extracted views of the unchanged dual proposal fold. It
  covers both receivers, lags 1/3/5, uneven tails, extreme samples, and two
  offsets. The physical result is `physical-arm/fold.json`.
- The public component test compares a positive DS9 dwell for both extracted
  receivers. It covers dense stride 10 ordinary, sparse stride 120 ordinary,
  sparse fractional, layout and capability queries, bounds and output
  atomicity, handle guards, rounding and nonfinite rejection, BUSY, and
  lifecycle. The physical result is `physical-arm/api-ds9.json`.
- The panel test holds contexts by template edge and detector mode across 80
  unique recorded dwells. Ordinary and fractional sparse results for both
  extracted receivers match their dual rows exactly, including all candidate
  scientific fields, proposal decisions, and deterministic work counters.
  Empty rows are valid and compared as empty. The physical result is
  `physical-arm/panel.json`.
- `dual-ordinary80-parity.json` separately freezes the unchanged dual ordinary
  output: 80/80 non-timing rows and their projection digest match the prior
  qualified output.

`panel-inventory.json` binds 80 unique content-addressed CI16 files, all four
templates, and all eleven schedule files. Regenerate it without changing data:

```bash
python3 reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/verify_panel_inventory.py \
  reports/2026_09_30_native_adaptive_deployment/ds9/portable80/fixtures \
  reports/2026_09_30_native_adaptive_deployment/ds9/portable80/schedules \
  reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/panel-inventory.json
```

The older board `paired80.tsv` is eight saved inputs repeated ten times. It is
a pacing and repeatability workload, not this 80-unique-dwell scientific panel.
The eleven `portable80/schedules` files are the authoritative full inventory.

Run the host panel against the existing build with:

```bash
reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/build-host/test-single-rx-panel \
  reports/2026_09_30_native_adaptive_deployment/ds9/portable80/fixtures \
  reports/2026_09_30_native_adaptive_deployment/ds9/portable80/schedules
```

The physical saved-data command was:

```bash
/mnt/glrtbench/native-adaptive/current/measure-run 600 \
  /mnt/glrtbench/native-adaptive/tests/single-rx-detector-v1/test-single-rx-panel \
  /mnt/glrtbench/ds9-native-comparison-20260930 \
  /mnt/glrtbench/native-adaptive/tests/single-rx-detector-v1/schedules
```

That physical panel passed 80 ordinary and 80 fractional dwells for both
receiver views in 32.525136750 seconds wall time, with 92,616 KiB maximum RSS.
This whole-process number includes one dual and two single calls per dwell in
each mode and is not per-dwell production latency.

## Scope

This qualifies native single-versus-dual scientific equivalence for saved DS9
data and the Cortex-A9 arithmetic path. It does not qualify server scientific
parity, live capture, sustained real-time execution, a Raspberry Pi, or an
RTL-SDR device or transport. No production CLI selects this API yet, no live
application was activated, and no RF was used. The separate RTL-SDR readiness
audit records the remaining transport and timing-authority work.

`build-arm/` is a retained failed build attempt: it used the non-plugin-aware
cross `ar` with LTO objects. `build-arm-final/` uses the matching `gcc-ar` and
is the qualified ARM closure.
