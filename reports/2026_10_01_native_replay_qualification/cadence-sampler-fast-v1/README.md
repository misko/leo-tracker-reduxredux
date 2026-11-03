# ARM memory-observer cost

The cadence controller originally parsed every `/proc/PID/stat` field into a
vector of strings once per second. The replacement scans tokens without that
allocation, retaining process-group and RSS meaning, including process names
with spaces or parentheses. Component tests compare it with the kernel record
and reject malformed, truncated, or negative numeric fields.

An idle PLUTO+ control/new/new/control sequence, 100 samples per process, measures
mean CPU of 1.123545 seconds for control and 0.684428 seconds for the new parser:
**39.08% less CPU**. Whole-process timings include executable startup. This is
an idle observer calibration; it does not isolate the cause of the full-chain
failure or establish loaded throughput. Binaries, source and timing receipts
are retained here; the original control is in `../cadence-sampler-cost-v1/`.

At a one-second sampling interval the new sampler still costs roughly two CPU
seconds per 300-second scan. Aggregate RSS sampling is diagnostic and can miss
transient peaks regardless of interval. Per-stage high-water RSS remains
available from the measurement wrapper. A configurable sampling interval can
reduce monitoring cost while preserving numerical and work-accounting gates.
