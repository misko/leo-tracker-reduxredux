# Counter-to-UTC authority

`Timebase` retains a bounded history of measured clock/counter brackets. A
single acquisition owner calls `read_bracket` using a current coherent hardware
counter. `PosixClock` supplies the monotonic and realtime reads; its counter port
can wrap `leo_local_source_snapshot`. Software delivery ordinals are rejected.
The caller must begin a new generation following a counter reset or clock step.

Each projection uses the latest anchor preceding its window. The uncertainty
includes the outer monotonic bracket, clock resolution and configured rate drift
through the end of the support. Anchors expire explicitly. Configure retention
to cover detector lag, refresh on the acquisition owner, and serialize readers
or give them value-owned snapshots. Never read the source from detector workers.
Correct system UTC does not remove the need for this measured mapping.

`ingest::project_event` connects scanner v2 fractional candidate events to the
public projection contract. Invocation identity and the sky RF/channel map must
be explicit. Queue latency never substitutes for observation UTC. This bridge
does not certify server detector parity and does not itself start hardware.

Tests: `bash native/adaptive/timing/build.sh /tmp/timebase` then
`/tmp/timebase/test-timebase`. `SANITIZE=1` enables ASan/UBSan. Use `ARM=1` with
the cross `CXX` for PLUTO+. The test uses synthetic counters and POSIX clocks;
it performs no RF acquisition.
