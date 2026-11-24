# DS30-0419 first-member idle staging amendment

Carry forward the original signed DS30-0419 inventory and the already
enrolled first member of the first segment. The only payload is
`iq-000000.ci16.zst`, **79,163,761 compressed bytes**, mapping to **64
original stereo visits** and **102,400,000 decoded bytes**. Keep the
original manifest, index, raw authority, recording/session identity,
and visit chronology. No other member or recording is authorized.
The earlier zero-residency deferral remains a separate result.
[Original enrollment](first-member-0419.md)

Take one bounded idle opportunity of at most **120 seconds**. Use the
original low-load interlock with full I/O PSI below 20%, device queue at
most two, and a measured quiet interval. Acquire the shared Gauss
lease only around each sequential physical read. Pace to at most
**2 MiB/s**, request at most **1 MiB** per read, and set random file
advice to suppress filesystem read-ahead. Use CPU 2, nice 15 and idle
I/O priority. Preserve the partial local extent if the gate expires or
device stalls force a stop. Record paid time, payload bytes, block I/O,
read sizes, admission waits and pauses. Stage in private `/tmp` tmpfs.

Admit exactly one receiver pair after full compression, index and
member digests verify. The odd-ID rule runs the frozen verify-once
20/8 ms candidate first and the installed-v3 20 ms detector second,
both on the staged bytes. Verify decoded data and per-visit digests
on the normal respective paths, preserve signed original visit
index, times and both lanes, then seal detections. Compare admitted
and excluded visits, factor and occupied-lane counts, shared CFOs
and complete process CPU/wall. Stop at detections. No solver,
new acquisition, other waveform read or full-recording speed inference.
