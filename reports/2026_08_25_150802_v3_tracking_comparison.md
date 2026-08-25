# V3 tracking comparison: `cap-20260825T150802-473cb5bbcbd6`

Generated from commit `36eb6474d92121f01cf992171add92bcd972d6ca` on the 53 persisted Standard-qualified 75 ms continuity arcs. The replay hash is retained verbatim for provenance; the relevant V3 source and DSP tests are byte-identical to the remotely reachable main-line implementation commit `197c1f25b30bab45ddcdc1f0b0ae12a20df63d73`. The primary display window was frozen before replay as the arc with the greatest persisted exact-minus-control coherence margin: stream-0/rx0, 1.650–1.725 s.

## Primary frozen window

| estimator | effective spacing | rate / final rate | comparison to 1.333 ms frame-CFO line |
|---|---:|---:|---:|
| GLRT20ms | 20 ms estimator, 25 ms cadence | line -4363.6 Hz/s | 44.2 Hz RMS at its three epochs |
| frame CFO | 1.333 ms | robust line -3223.2 Hz/s | 16.2 Hz line residual RMS |
| V2 tracking | 1.333 ms updates | final -2893.2 Hz/s | signed rate error +330.0 Hz/s |
| V3 tracking | 1.333 ms updates after acquisition | final -3220.9 Hz/s | signed rate error +2.3 Hz/s |

Both trackers supported and updated all 55 frames and qualified modulo-pi phase lock. V3 searched 3334 integer epochs × 17 CFO hypotheses, kept epoch 865 (0-sample circular change), and moved the CFO seed by -100 Hz. Its held-out exact/control alignment scores were 0.2637/0.2504, margin 0.0133.

## Capture-wide paired replay

- V2 completed 53/53 arcs; V3 completed 53/53; 53 pairs had at least three supported frame-CFO points on both sides.
- V2/V3 phase-lock qualification: 53/42 arcs.
- Among the 53 line-comparable pairs, V3 had the lower absolute final-rate error versus its own independent frame-CFO line in 22 arcs.
- Median absolute final-rate error: V2 138.2 Hz/s; V3 171.1 Hz/s. 90th percentile: V2 346.5; V3 450.2 Hz/s.
- Median tracked-CFO RMS versus the local frame-CFO line: V2 25.2 Hz; V3 9.7 Hz.
- V3 changed the frame epoch in 5/53 arcs (maximum circular shift 1 samples) and the CFO seed in 48/53 arcs (maximum |shift| 250 Hz).
- V3 is deliberately less certain: median final rate sigma 680.6 Hz/s versus V2 63.4 Hz/s.
- Replay binding matches the Standard builder: `(source trajectory, probe)` model CFO plus the persisted candidate frame epoch; 1 sparse returned-track gap required the recorded branch-matched detection fallback.
- Baseband edge mapping follows the random tunings: stream-0 lower at 1.2096875 GHz; stream-1 upper at 1.6903125 GHz.

## Interpretation

There is no external Doppler truth here. “Closer” means closer to a robust degree-one line fitted to the independently measured frame CFO on the same acquired lattice. It tests local consistency, not orbit-level accuracy. GLRT20ms is much more sparsely sampled, so its three-point local slope is particularly noise-sensitive.

V3 is research-only and is not part of the Standard persisted pipeline. The Standard artifacts used here supplied immutable segment selection and GLRT inputs; this replay created additive report artifacts only. The recording is manifest V2 while this checkout's typed reader accepts V1, so the replay used a narrow read-only `ci16_le` extractor and verified all 4 consumed compressed chunks against their manifest SHA-256 values.

## Evidence

- [Tracking comparison figure](figures/2026_08_25_150802_v3_tracking_comparison/tracking-comparison.png)
- [Source-bound comparison results](figures/2026_08_25_150802_v3_tracking_comparison/comparison-results.json)
