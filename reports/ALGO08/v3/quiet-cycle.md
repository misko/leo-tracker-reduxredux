# Three quiet checks failed to predict which searches could be skipped

On weak physical DS30-0016, two empty full-length observations with an empty short observation between them still concealed native detections in **13 of 58** apparently quiet single-radio groups. Skipping their other short searches would lose **30 of 401** positive short lanes. Requiring both radios to agree still lost **23**. A positive lane here means the 12 ms receiver passed its existing fractional verification gate. [Frozen experiment](quiet-cycle-protocol.md) · [Replay and clock bindings](quiet_cycle.py) · [Counts and timing receipt](measurements/quiet-cycle.json)

Within each exact pilot edge, channel and RF stream the proposed rule always measures slots 0, 4 and 8. It can skip six other short calls per radio in a complete quiet group. The stereo rule requires all six checks across both radios to be empty. The last full anchor closes one interval and opens the next. Incomplete trailing intervals retain all searches. The calculation grants free buffering and access to the final anchor before choosing the skipped calls. All original compressed-file validation would still be required.

| Genuine saved input | Short calls / native positive lanes | Policy | Calls avoided | Positive lanes lost | Quiet groups containing misses | Calls avoidable with perfect group veto |
|---|---:|---|---:|---:|---:|---:|
| DS30-0016, physical weak | 1,240 / 401 | Single radio | 348 | 30 | 13 / 58 | 270 |
| DS30-0016 | | Stereo | 60 | 23 | 5 / 5 | 0 |
| DS30-0008, physical dense | 11,834 / 6,380 | Single radio | 834 | 86 | 49 / 139 | 540 |
| DS30-0008 | | Stereo | 108 | 15 | 4 / 9 | 60 |
| North, public simulation | 2,096 / 996 | Single radio | 672 | 224 | 104 / 112 | 48 |
| North | | Stereo | 456 | 156 | 37 / 38 | 12 |

The last column grants an ideal predictor that restores all six searches in every group that contains even one missed positive, or all twelve for a stereo group. It keeps every original measured positive. On weak, the native short calls cost **1.282 CPU s for 1,240 calls**, an average **1.034 ms per call**. Valuing each avoided call at this mean, the single-radio decision gives **0.360 s** before any repair and **0.279 s** with ideal group repair. The stereo rule with ideal repair saves zero on weak. The actual per-lane execution costs vary, so these are projections from exactly counted calls. Neither rule advanced to a new position fit or waveform benchmark. [Original warm CPU and complete publication](unified-short-layout.md)

**A receiver that can screen individual lanes has a narrower target.** For the illustrative weak acquisition goal of 3.392 → 2.700 s, an otherwise free gate needs to skip **670 of 839** empty short lanes at the measured mean cost, keeping every native positive. If the gate really costs 50 µs for each of the 1,240 short lanes, it needs **730 of 839** empties. Even identifying all 839 would leave only **141 µs per short lane** for screening. This tests one way to fund the acquisition share of the two-recording speed budget. Lower-cost searches that still measure a positive, faster authenticated input or greater savings elsewhere change the required rate. [Joint timing budget](successor-design-review.md)

Reproduce with `python3 -B reports/ALGO08/v3/quiet_cycle.py` on the saved packet host. It checks each original packet SHA-256, the clock receipt digest, the native clock’s packet identity, and the weak call and positive counts. Three component tests cover paired radios, RF interleaving, shared anchors, tail handling and the group veto. No surveyed position, orbit, known site, waveform or additional acquisition enters the calculation.
