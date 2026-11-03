# Bounded 32-dwell queue qualification

The preceding queue-16 run rejects seven dwells at 101.44–124.72 seconds into
its second scan. There are no detector computation failures. Its first complete
downstream chain passes every scientific control and finishes in 297.447 seconds,
but that does not qualify lossless operation. A counterfactual calculation using
measured service durations and neighboring median/max service estimates for
missing dwells predicts a peak queue of 23–25 and maximum latency of 3.23–3.43
seconds. This is a sizing estimate, not a hardware guarantee.

This run changes only the explicit detector queue limit from 16 to 32 and the
diagnostic's permitted maximum. Detector science, priorities, arrival origins,
PGO seed/tracker/positioning builds and five-second monitoring remain unchanged.
The IQ pool stays bounded at queue capacity plus two: at most 34 buffers of
2,400,000 bytes (77.82 MiB), an increase of 36.62 MiB over the previous limit.
No samples are discarded, decimated or thresholded to obtain more capacity.
Overflow remains an explicit failure.

Acceptance was set before execution (`acceptance-policy.json`): four complete
scans with exact science and zero dropped dwells; all three loaded downstream
intervals under 300 seconds and complete before the next scan is ready; detector
arrival-to-finish latency no greater than 5 seconds; queue and buffer usage within
their declared limits. The last downstream interval is an unloaded drain and
cannot count as loaded-throughput evidence. Report aggregate/per-stage memory.

## Physical result: passed

All four scans completed with 2,215/2,215 dwells, 16,191 observations per scan,
zero rejections or computation failures, and exact pinned detector, projection,
seed, track and association controls. All 400 search scores pass the independent
host tolerance. `evaluation.json`, `loaded-cadence-evaluation.json` and
`acceptance-evaluation.json` retain the checks.

| Scan | Peak queued dwells | Maximum dwell latency (s) | Downstream wall (s) |
|---|---:|---:|---:|
| 0 | 2 | 0.324 | 297.086 |
| 1 | 14 | 2.021 | 297.852 |
| 2 | 21 | 2.913 | 297.688 |
| 3 | 11 | 1.602 | 252.731 (unloaded drain) |

All three loaded chains finished before the next scan became ready. The smallest
observed margin against 300 seconds is only 2.148 seconds. Peak IQ allocation
was 22 buffers, within the declared 34-buffer cap. Sampled aggregate process-tree
RSS peaked at 242,476 KiB; five-second sampling can miss peaks and double-count
shared pages. This is finite repeated-recording evidence, not a guarantee for
other recordings or simultaneous live RF acquisition.

The deterministic slow-detector tests exercise both a burst absorbed by the
larger queue and a larger overload that must still reject explicitly; invalid
capacities are rejected. All 108 benchmark tests pass. Raw IQ stays on PLUTO; this is
recorded-data qualification, not new RF acquisition.
