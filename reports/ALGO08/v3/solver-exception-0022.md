# Recovering the first archived ALGO08v3 interpolation failure

The current saved routed pipeline recovered **DS30-0022** in **39.812 s
wall / 39.781 s CPU** with a verified two-arm publication. It used the
previously qualified instance-level orbit support handler through the
original named retry. Both positions, conditional RF RMS values and
owner digests exactly reproduced the deployed ALGO08v2 fix. The earlier
25.174 s quadratic recovery had a different roster and increased fitted
position error by 109 m. [Earlier complete saved publication](short-graph-and-geography.md)

| Comparison scope | Wall / CPU, s | Fixed-zero / fitted horizontal error, km | Fixed-zero / fitted RF RMS, Hz |
| --- | ---: | ---: | ---: |
| Archived ALGO08v2 raw through exit | 205.142 / 148.223 | 1.294 / 1.311 | 161.796 / 161.615 |
| Archived ALGO08v3 raw through failed exit | 110.770 / 53.464 | — | — |
| Earlier repaired v3 saved solve before figures | 38.848 / 34.329 | 1.294 / 1.311 | 161.796 / 161.615 |
| Earlier quadratic saved publication | 25.174 / 24.686 | 1.292 / 1.419 | 147.976 / 147.984 |
| **Current repaired saved publication** | **39.812 / 39.781** | **1.294 / 1.311** | **161.796 / 161.615** |

The controls were historical. Each row gives its own measurement
boundary. The saved child cannot supply the acquisition time or a
raw throughput ratio for this recording. The reference is the original
operator site authority. Frequency fit and horizontal error differ
here even on the same packet. [Earlier repair and three saved controls](../single-core-2x/algo08v3-solver-orbit-support.md)

## Failure and repair

The released v3 cold receiver-smooth corner search asked the orbit
projector to interpolate outside its nominal support. The named retry
then called the same sparse instance method again. Sparse ranking
installs `shifted` on the scan instance, which takes precedence over
the released retry's wrapper on the class. In the current composition,
the named retry wraps the bound instance method. It authenticates the
nominal bank and phase/derivative domain, obtains only required new
states from the same causal SGP4 catalogue and checks the unchanged
seam. The orbit projector still forbids extrapolation.
[Existing repair source](../../../tools/pipeline_eval/variants/v5_orbit_domain.py)

The earlier-orbit census chose lean because its sampled history was
healthy. Its first attempt still hit the interpolation exception.
The retry propagated only the **−18 s** knot. Across eight extended
corner projections it added 232 satellite states and checked the
existing neighboring knots in the same native propagations. The new
support took **27.6 ms wall**. The retry's lean inference then rejected
its own proposed support repair under the original 5% cap, with
131/2,159 curved rows, 13/258 predictive rows and 5/63 tracks removed.
The separately paid named fallback completed. The complete solve was
**36.624 s wall / 36.594 s CPU**, including both attempted routes.
The visible terminal declares `orbit_support`. The earlier portable
archive index acted on 19 bodies with two cold bodies in each of the
two preparations. A healthy earlier-orbit census did not detect the
nominal support boundary in this recording.

The verified result used the original **6,772 issued visits, 5,268
admitted visits, 10,536 probes and 3,989 factors**. Both arms used
the same 2,388 ordered owners, with 2,099 conditional and 289
predictive rows. The publication completed all 179 grid positions,
the bound fit path and eight independently verified PNGs, with the
four original orbit sheets and conservative renderer active. The
signed region and raw authority were unchanged. The original v3
failure had no position result.

## Source availability and cost

The lowest ID among the five historical exceptions had its exact
native bytes in the existing tmpfs panel copy and an authenticated
inventory from the previous saved result. Its 46 pre-capture
catalogue names reconstructed the original archive digest from
existing staged donors. All **82,257,519 bytes** were resident and
verified against the original content names, then hardlinked within
tmpfs without copying the catalogue bodies. The existing inventory,
offer and 4,303,738-byte saved detector document totalled 4,307,946
bytes read for input admission, recorded separately as **0.430 s
wall / 0.390 s CPU**. The child admitted one saved packet, enabled
the waveform denial ports and never opened the original paths.
It recorded 408 process input blocks and seven major faults,
without a file-level attribution. The readiness census confirms
the catalogue resides in tmpfs.

The other four original saved-pair receipts also end in the same
interpolation exception. A metadata-only donor census reconstructed
the exact original archive name commitments for DS30-0129,
DS30-0234, DS30-0239 and DS30-0247 (51, 50, 49 and 49 snapshots).
Those four payload sets were not reverified and no other child ran.
The previously published instance-level repair recovered DS30-0129
with different owners and worse errors than v2, and DS30-0239 with
exact v2 results. This one current success leaves the original panel
failure count and its timing accounting unchanged.

As-run freeze `19ceca9e6`. Eleven targeted tests passed, including
the original sparse instance regression, the causal seam and the
new donor archive commitment control. [Protocol](solver-exception-0022-protocol.md)
· [Machine receipt](measurements/solver-exception-0022.json.gz), SHA-256
`d9e33461bbbf867d282002d4bf9b3139dec3e47f464b898aa1ff1bd6717ad4b8`
before compression.
