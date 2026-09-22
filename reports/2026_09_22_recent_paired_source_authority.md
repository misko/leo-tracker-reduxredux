# RF-only paired-source authority on the recent 300-second scan

This bounded audit uses saved IQ-derived fractional-GLRT products from
`scan-fw-1d05092feaa8f7d5`. It uses no observer position, TLE identity, saved
site-conditioned candidate list, calibrated phase, beam response, or fixture
boresight. It does not collect RF.

Within the same visit, RF channel and spectral edge, pilot epochs must agree
within nine samples modulo the pilot period. A differential RX1-minus-RX0 CFO
intercept and drift is fitted on even visits modulo the unresolved 227.27 kHz
pilot alias. Odd visits are held out. A CFO-gated edge is accepted only when it
is mutually unique for both receiver detections. The epoch is placed on the
common visit sample clock by adding each probe's sample offset. Shifted controls
at 17 and 53 visits break simultaneity while retaining lane-compatible comparisons.

The scan contains 4,651 qualified receiver-local detections. There are 223
training timing edges and 222 held-out timing edges. The frozen offset model
admits 215 mutually unique held-out matches. The 17- and 53-visit controls have
105 and 112 lane-compatible comparisons respectively, and zero matches in both.
Mapping those matched GLRT candidates into the independently reconstructed
track graph by source group, lane and alias-equivalent selected CFO yields 10 RX0/RX1
track-pair authorities with at least three
distinct held-out anchor visits. Their per-link offset residual RMS ranges from
121.1 to 262.3 Hz. The strongest link has 27 distinct anchor visits.

This establishes RF evidence that each admitted pair of receiver-local paths
contains repeated observations of one common pilot waveform. It does not
identify a satellite and does not resolve the pilot-symbol frequency alias.
The authority can feed the visit-balanced paired Doppler factor, which compares
a shared candidate against an independent-receiver ablation and profiles one
constant offset per receiver path using training observations only.

Generic full-band IQ coherence was deliberately not added to the gate. A
broadband common component can contain other simultaneous energy and is not
carrier-specific by itself. Here carrier specificity comes from the fractional
GLRT pilot epoch, lane, and CFO evolution. Broadband coherence remains suitable
as corroborating quality evidence after this source-specific association, not
as a replacement for it.

The nominal LT3D-001A ring spacing is 80 mm. Even if it were the electrical
phase-center baseline, 11.2 GHz, 8 km/s relative speed and 500 km slant range
bound its differential Doppler near 0.048 Hz. The measured benefit is extended
temporal Doppler support, not spatial triangulation across the holder.

Artifacts:

- `2026_09_22_recent_paired_source_authority/receipt.json`
- `tools/research/audit_recent_paired_source_authority.py`
- `src/leo/analysis/research/paired_receiver_geometry.py`

The receipt binds the immutable capture, analysis, raw recording authority and
input shard digests. It retains every authorized link, its anchor visits,
residual RMS, epoch skew, unresolved-alias state, and `identity_claimed=false`.

## Matched blind-grid comparison

A subsequent truth-free comparison replayed the strongest scan on each of the
three independently declared 50 km global grids. Authority-building rows were
removed from both arms. Nine links retained at least two training and two
held-out observations on both paths under one visit-level chronological split.
One link did not and is recorded as excluded; its original independent score is
retained identically in both totals. The independent arm assigns effective
count three to each receiver path, while the paired arm assigns effective count
six to their combined visits. Both therefore contribute six per admitted pair.
Both use the full causal catalogue prior denominator, an explicit null, the
same nominal orbit states, and separate constant receiver-path offsets.

| Declared branch | Independent selected cell | Paired selected cell | Independent held-out | Paired held-out |
|---|---:|---:|---:|---:|
| Sacramento | 37.9040, -122.3492 | 37.9040, -122.3492 | 740.780 | 748.519 |
| Denver | 37.7384, -122.4355 | 37.7384, -122.4355 | 727.016 | 733.499 |
| Reno | 37.9273, -122.3791 | 50.5384, -108.8813 | 736.036 | 441.750 |

The Sacramento and Denver branches retain the same selected cell and gain 7.74
and 6.48 held-out composite-score units. The Reno paired training optimum moves
to a different basin whose held-out score is 294.29 lower. Thus the paired
constraint supplies real information but does not remove broad-region mode
ambiguity reliably in this single scan. These are composite, uncalibrated scores
conditional on retrospective RF-only pair extraction; they are not posterior
probabilities or calibrated likelihood-ratio significance. No branch was chosen
using reference position, and no position truth was accessed by the comparison
runner.

The 250 km benchmark used 275 MiB peak RSS and 10.6 seconds on one thread. The
full Sacramento run used 305 MiB and 2:35; Reno and Denver ran concurrently and
stayed below 293 MiB each. The execution receipt binds each result and log plus
snapshots of the exact paired factor, regional scorer, and comparison runner.

Additional artifacts:

- `2026_09_22_recent_paired_source_authority/recent-paired-blind-sacramento-validated-v3.json`
- `2026_09_22_recent_paired_source_authority/recent-paired-blind-reno-validated-v3.json`
- `2026_09_22_recent_paired_source_authority/recent-paired-blind-denver-validated-v3.json`
- `2026_09_22_recent_paired_source_authority/paired-comparison-execution-receipt.json`
- `2026_09_22_recent_paired_source_authority/executed-sources/`
