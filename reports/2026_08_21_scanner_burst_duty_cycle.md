# Scanner burst duty-cycle review

Date: 2026-08-21  
Scope: ten newest complete four-scan bursts in the local production scanner store  
Source: immutable manifests beneath `/srv/bulk/leo/scanner-recordings`  

## Result

Each burst contains four complete scans. Each scan covers eight Starlink
channel/edge targets and records 80 ms per target at 2.5 Msps. RX0 and RX1 are
captured simultaneously, so receiver time is not double-counted when computing
radio duty cycle.

- Recorded duration per scan: `8 * 0.080 s = 0.640 s`
- Recorded duration per four-scan burst: `4 * 0.640 s = 2.560 s`
- Mean within-burst RF duty cycle: **48.44%**
- Mean individual-scan RF duty cycle: **68.28%**
- Mean capture-to-durable duty cycle: **26.51%**

The burst RF duty is highly repeatable: its sample standard deviation is 0.42
percentage points, its range is 1.35 percentage points, and its coefficient of
variation is 0.88%.

## Definitions

Three related measurements are reported separately:

1. **Recorded time** is the sum of `sample_count / sample_rate_hz` over the
   manifest's frames. It measures requested RF sample time and does not count
   simultaneous receivers twice.
2. **RF capture span** runs from the earliest
   `host_request_utc_ns_lower` to the latest `host_request_utc_ns_upper` in the
   burst. RF duty is `recorded time / RF capture span`.
3. **Durable span** runs from the earliest manifest `created_utc_ns` to the
   latest `finalized_utc_ns` in the burst. It includes compression, hashing,
   fsync, and atomic bundle publication. Durable duty is
   `recorded time / durable span`.

The individual-scan duty column is the mean of the four values computed as
`0.640 s / scan RF capture span`. It shows tuning/listening efficiency inside
each scan, while burst RF duty additionally includes handoff gaps between the
four scans.

## Latest ten bursts

Times are UTC.

| Burst | Start | Radio | Recorded | RF capture span | RF duty | Mean individual-scan duty | Durable span | Durable duty |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `7e619cb033db4180` | 22:43:20.863 | 5d4d | 2.560 s | 5.331 s | 48.02% | 67.49% | 10.067 s | 25.43% |
| `5245b3272a2c4280` | 22:39:26.252 | 19f2 | 2.560 s | 5.259 s | 48.68% | 68.22% | 9.774 s | 26.19% |
| `2c0ca1426de546ef` | 22:29:33.188 | 5d4d | 2.560 s | 5.369 s | 47.68% | 67.53% | 9.680 s | 26.45% |
| `56e2f8dff6a04dd2` | 22:25:15.563 | 19f2 | 2.560 s | 5.221 s | 49.03% | 69.95% | 10.059 s | 25.45% |
| `ec9fa603b96a495a` | 22:21:03.073 | 19f2 | 2.560 s | 5.248 s | 48.78% | 68.35% | 10.272 s | 24.92% |
| `b144bd37d7894d73` | 22:17:06.471 | 5d4d | 2.560 s | 5.260 s | 48.67% | 68.35% | 9.331 s | 27.44% |
| `05e62a10f89e4c9c` | 22:06:00.124 | 19f2 | 2.560 s | 5.298 s | 48.32% | 68.86% | 9.568 s | 26.76% |
| `89d7537ed6a2402e` | 22:01:42.800 | 5d4d | 2.560 s | 5.316 s | 48.16% | 68.41% | 9.556 s | 26.79% |
| `7e43a601dd8d4816` | 21:57:30.032 | 5d4d | 2.560 s | 5.308 s | 48.23% | 67.38% | 8.965 s | 28.56% |
| `effe5d13c2cf47b3` | 21:53:34.167 | 19f2 | 2.560 s | 5.243 s | 48.83% | 68.29% | 9.425 s | 27.16% |

## Aggregate statistics

| Metric | Minimum | Mean | Median | Maximum |
|---|---:|---:|---:|---:|
| Recorded time per burst | 2.560 s | 2.560 s | 2.560 s | 2.560 s |
| RF capture span | 5.221 s | 5.285 s | 5.279 s | 5.369 s |
| RF duty cycle | 47.68% | 48.44% | 48.50% | 49.03% |
| Mean individual-scan duty | 67.38% | 68.28% | 68.32% | 69.95% |
| Durable span | 8.965 s | 9.670 s | 9.624 s | 10.272 s |
| Durable duty cycle | 24.92% | 26.51% | 26.60% | 28.56% |

The ten bursts span 2,992.027 seconds from the first RF request in the oldest
burst to the final RF response in the newest burst. They contain 25.6 seconds
of requested RF samples, giving an overall calendar scanner duty cycle of
**0.856%** across that observation interval.

## Interpretation

A typical individual scan records 640 ms over approximately 940 ms, so about
68% of its RF capture span contains requested samples. A four-scan burst
records 2.56 s over approximately 5.29 s, reducing duty to about 48% after the
handoffs between scans are included.

Durable publication finishes in approximately 9.67 s on average. The gap
between the RF span and durable span is storage work rather than lost samples:
compression, checksums, manifest creation, fsync, and atomic publication occur
after acquisition. If scanner cadence needs to increase further, RF handoff
overhead and durable publication should be measured and optimized separately.

## Reproduction method

For each complete `scan-burst-*` group, the review:

1. grouped the four `-01` through `-04` manifests by burst prefix;
2. required exactly four manifests;
3. summed frame duration from authoritative `sample_count` and
   `configuration.sample_rate_hz`;
4. computed RF span from the frame request bounds;
5. computed durable span from manifest creation/finalization bounds; and
6. sorted groups by RF start time and selected the newest ten.

No IQ payload was decoded or modified. No catalog, service, radio, or QNAP
state was changed during this read-only review.
