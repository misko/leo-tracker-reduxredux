# Four-scan fixed-cadence qualification candidate

**Failed lossless qualification.** Recovered device receipts show that scan 0
completes every scientific comparison and downstream processing in 297.446711
seconds. Scan 1 completes 2,208 of 2,215 dwells and rejects seven when its
16-dwell queue fills. Its detector exits 3; the controller reports a child failure.
The host observer exits 143 without a complete controller receipt. No experiment
processes remain on the device, and partial products were recovered separately.
This is not a successful four-scan run. `scan-0-evaluation.json`,
`scan-1-partial-evaluation.json` and `queue-diagnosis.json` retain the evidence.
The seven drops occur between 101.44 and 124.72 seconds of scan 1. A bounded
queue-32 candidate is tested separately in `../cadence-four-queue32-v1/`.

Prepared before execution. This experiment repeats the existing 300-second
DS9 recording four times at fixed 300-second origins. It combines the qualified
seed/curvature PGO candidates and freshly profiled prepared-threshold scorer,
with the existing catalogue index. Detector, queue capacity, priorities,
five-second memory sampling and numerical/search policies stay unchanged.
All IQ remains on PLUTO+. No new RF is collected.

The scientific and scheduling acceptance gates are:

- Four complete observation/support checkpoints, each with 2,215 dwells and
  16,191 positives; zero rejected/dropped dwells.
- Every detector checkpoint, seed and track output matches its frozen control;
  all 400 search points match ARM control, independent host tolerance passes,
  and final associations match host.
- Fixed origins remain 300 seconds apart; execution stays within the declared
  detector and pending-scan capacities, without rebasing or hidden retries.
- Each of the first three downstream jobs finishes before the next completed
  scan is ready. Their measured duration must also be below 300 seconds.
  The fourth downstream job is an unloaded drain and cannot establish loaded
  throughput. Finite completion alone is insufficient if waiting grows.
- Record whole-process stage CPU/wall/RSS, dwell latency, queue high-water marks
  and sampled aggregate RSS; report sampling limitations explicitly.

This establishes only the measured repeated-recording load horizon. It does
not supply longer scientific history, qualify live acquisition, establish Pi
performance, or make native tracking identical to server tracking.

`protocol.json` pins all payloads and arguments. Start only after the complete
ARM position trial in `../prepared-threshold-full-v1/` passes. Preserve failed
attempts; never restart into the same result directory.

The predeclared loaded-throughput gate is implemented in
`tools/evaluate_loaded_cadence.py`. After `tools/evaluate_arm_cadence.py` writes
the combined scientific/scheduling receipt, run:

```sh
PYTHONPATH=src:tools python tools/evaluate_loaded_cadence.py \
  reports/2026_10_01_native_replay_qualification/cadence-four-threshold-pgo-v1
```

It requires at least three loaded intervals, checks each against the 300-second
deadline and next-scan readiness, excludes the final drain, and requires the
scientific/lossless receipt to pass. It refuses to overwrite previous results.
All 104 benchmark/scheduling tests pass (`bench-tests.log`). Applied to the
previous `cadence-three-observer-v2/` report, it correctly fails loaded throughput
despite that experiment's exact science and zero dropped dwells.
