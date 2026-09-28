# Reno 12:50 long-track association diagnosis

Scan: `scan-fw-d86e8f23c0624bac`, 2026-09-26 12:50 UTC. Published Reno location error: 706.761 km; fitted location 41.771916, -115.969934. This is a post-hoc diagnosis, not a change to either independent-prior search. No Sacramento proposals or assignments enter this analysis.

## Finding

There is strong model-based evidence of incorrect satellite associations on long tracks, not merely short ambiguous tracks. All 11 tracks spanning at least 30 seconds select different satellite IDs when evaluated at the known receiver coordinates. All 46 tracks change their preferred identity overall. These are reference-conditioned model comparisons, not independently decoded satellite identities.

| Track prefix | Span seconds | Occupied-second weight | Reno satellite | RMS at Reno's wrong location, Hz | Same satellite at reference, Hz | Best reference satellite | Its RMS at reference, Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| ad00e08d | 51.72 | 49 | 63780 | 196.12 | 39,280.95 | 63850 | 525.62 |
| d4446f2d | 50.59 | 45 | 63780 | 101.03 | 30,365.52 | 63850 | 474.21 |
| 46b5f08c | 40.25 | 31 | 63771 | 307.93 | 26,674.98 | 61518 | 42.44 |
| 46d4ff4a | 35.89 | 31 | 69951 | 176.09 | 21,028.37 | 65465 | 140.91 |
| f2a49cfa | 35.39 | 32 | 63771 | 265.35 | 20,532.06 | 61518 | 168.36 |

IDs are catalogue numbers. Span is last observation minus first observation, not continuous RF dwell duration. All RMS values use the original evaluation observations after fitting a constant frequency offset and tau on training observations. For the reference check, even the original Reno IDs are allowed to refit their offset and tau over the same -5 to +5 second grid. Their large reference errors are therefore not just frozen-parameter mismatches. All original Reno identities were returned as visible at the reference site; this is a Doppler-trajectory mismatch, not simple horizon exclusion.

The 40.25-second track is a particularly clear example: satellite 63771 fits badly at the actual receiver location (26.7 kHz), while satellite 61518 fits at 42.4 Hz, with training RMS 42.3 Hz and tau zero. Its next-best reference candidate has 1,968 Hz evaluation RMS. Training-only and evaluation-based selection agree on 61518.

## Why long tracks did not prevent the error

At the wrong location, the two longest tracks strongly prefer 63780: their original best-versus-runner-up gaps are 1,913 and 1,511 Hz. Previous conditional top-three resampling selected this ID in all 32 randomized whole-second-bin splits for each track. This establishes conditional stability, not correctness. Small-margin rejection would not flag them.

Conversely, the correct-location best fits for those longest tracks are still 474–526 Hz and both reach the -5-second tau boundary. The wrong-location/wrong-identity explanation actually has a lower residual (101–196 Hz). The model can therefore favor the wrong joint explanation even with relatively long tracks. Boundary hits and poor correct-site fit warrant investigation of timing/orbit-model error, frequency dynamics, or track construction; this experiment does not establish which causes that mismatch.

The two longest tracks overlap almost completely in time (about 62.6–114.3 seconds into the capture), so they should not be assumed independent pieces of satellite evidence. They contribute 94/892 = 10.5% of the occupied-second weight; the recorded evidence alone does not establish their independence.

## Scope and reproducibility

`analyze.py` reads the immutable position document through its public storage port, reconstructs the same evidence and causal TLE snapshot, asserts both digests, and scores the full original catalogue at the reference location only. It retains the original Reno result unchanged. Reference location: 37.84903264307456, -122.4856541910174. `results.json` records every track, original fit, top-three reference candidates, training-only winner, and the original identity re-fitted at reference, plus document/evidence/snapshot bindings.

The earlier prototype files supply only the original Reno margin and conditional resampling diagnostics. Shared candidate improvements from those experiments are not used as evidence of valid independent-prior performance.

This analysis supports calling these associations inconsistent with known receiver geometry under the current Doppler/TLE model. It does not prove the alternative catalogue labels are the transmitting satellites: no independently decoded satellite-identity ground truth is available here. Evaluation observations are reused diagnostically, not presented as an independent validation set. No production code, search result, or RF collection changed.
