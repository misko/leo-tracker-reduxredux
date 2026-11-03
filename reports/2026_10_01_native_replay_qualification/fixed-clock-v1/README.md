# Explicit replay clock qualification

The recorded detector now accepts `--start-monotonic-ns N`, using the Linux
`CLOCK_MONOTONIC` epoch shared by local processes. `--clock-now` reports that
clock for a controller. All dwell offsets remain relative to the supplied
origin; initialization and prior work cannot silently move it. A missed origin,
zero/overflow timestamp, or initialization lead exceeding 60 seconds fails.
Existing invocations retain their 100 ms initialization-relative start.

On PLUTO+ 192.168.1.15, 16 original recorded dwells started against an explicit
origin five seconds after the clock query. Initialization completed before
that origin, no arrivals were early, there were no drops, and every GLRT
candidate matched the preceding full-scan PGO control. Emitted observation and
support rows are exact ordered subsets of the complete frozen checkpoints.
The subset comparator correctly does not call this a complete-scan match.

`protocol.json` preserves requested origin, commands and payload hashes;
`detector.stderr` records actual origin and readiness on the device.
`comparison.json` and `checkpoint-subset-comparison.json` contain the checks.
The executable, source snapshots and ARM build log are preserved. The PGO GLRT
archive and FFTW inputs are the same as `../fullchain-index-pgo-overlap-v1/`.

34 host pacing, overlap and evaluation tests pass, including exact clock epoch,
no early processing, and rejection rather than rebasing of a missed start.
This is scheduling-boundary qualification, **not sustained pipeline evidence**.
Next connect bounded downstream work to successive completed observation/graph
products, with detector origins at `origin + scan_index * 300 seconds`.
Include process initialization, scan-boundary overlap, checkpoint publication,
downstream backlog and per-process/aggregate memory in that recorded load test.
Reuse of the same IQ must remain explicitly labeled a repeated-recording load
test, not a genuine longer scientific capture.
