# In-flight orbit support transfers to DS30-0129

The frozen DS30-0022 worker recovered the next archived interpolation
failure in **20.264 s wall / 20.259 s CPU** from its exact saved detector
packet. It extended the **+318 s** edge of the orbit bank in three
native requests, matching the earlier repaired v3 support counters.
The terminal reports `orbit_support`. The worker completed one
preparation and one inference with zero outer restarts.
[Frozen transfer](live-orbit-support-0129-protocol.md) · [Left-edge control](live-orbit-support.md)

The worker's ordinary earlier-orbit census selected lean. Its signed
prior was unqualified, and the original lean route accepted the fit
without named fallback. Both calibration arms, 3,915 owners per arm,
all 179 grid points, the bound fit path and all eight verified PNGs
published. This route's ownership and endpoints differ from both
archived comparators.

| DS30-0129 comparison | Wall / CPU, s | Horizontal error at c=0 / fitted, km | Conditional RF RMS, Hz | Owners per arm |
| --- | ---: | ---: | ---: | ---: |
| Archived v2 raw full process | 261.205 / 203.761 | 0.677780 / 0.611240 | 108.504 / 108.583 | 4,059 |
| Archived v3 raw failed exit | 67.634 / 66.455 | — | — | — |
| Earlier instance-guard repair, saved numerical solve before figures | 43.415 / 42.803 | 0.726135 / 0.689378 | 109.657 / 109.719 | 2,980 |
| **In-flight saved worker through complete exit** | **20.264 / 20.259** | **0.725427 / 0.698335** | **108.069 / 108.161** | **3,915** |

The current endpoints are **47.65 m and 87.10 m farther** from the
operator reference than v2, despite lower RF RMS by 0.435 and
0.422 Hz. Against the earlier patched solve, fixed-zero improved
by 0.71 m and fitted worsened by 8.96 m. It published 144 fewer
owners per arm than v2 and 935 more than the earlier repair.
Both owner digests differ. The prior numerical-only receipts
support a count and digest comparison. They provide no ordered
row intersection for this scope.
[Earlier recovered science](../single-core-2x/algo08v3-solver-orbit-support.md)

The fresh numerical stage, including its complete grid, cost
**16.742 s wall / 16.740 s CPU**. Within it the single preparation
was 2.314 s and the single inference was 14.300 s wall. The
in-flight extension cost 22.0 ms and preserved the exact original
seam. The numerical-only historical comparator exercised a
different inference route. Its 43.415 s is context for recovery
cost and does not isolate the acceleration from binding earlier.
The raw historical clocks use a separate acquisition boundary.

The original packet and exact inventory came from the existing
tmpfs v3 panel copy, preserving 6,767 issued visits, 6,752 admitted,
13,504 native probes and 6,475 factors. The 51-snapshot archive
reproduced the signed pre-capture commitment from local resident
copies. It was verified and linked without recopying its 91,154,379
bytes. The stage took 0.432 s wall / 0.430 s CPU. The same earlier
portable orbit artifact served eight bodies, with 24 handled by
the cold preparation path. The child reported four major faults
and 176 process input blocks with no file-level attribution. The
input hooks disallowed waveform and backing archive opens.
There was one complete candidate and no fresh comparator.

The transfer's admission test passed. The prior 15 native healthy,
boundary and dispatch checks apply to the unchanged worker.
Launch freeze `37e6c7576`. [Machine receipt](measurements/live-orbit-support-0129.json.gz),
SHA-256 `4fbe2ae5517dcbe304ddcf6fc1bc55b13f5ceaed38ebb7c4f0d8695f9504c548`
before compression.
