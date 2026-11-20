# Receiver recovery on 135 matched roof recordings

Compact secant and the archived native-agreement route both published all 135 recordings in each calibration arm. The paired 10% gate against original no-repair v5 was met in both arms on 131 recordings for compact secant and 130 for the cascade. Native clock plus offset OU published 114 in each arm and met the gate in both on 37. The RF preflight archive replay preserved the original no-repair position on all 135 recordings in both arms. [Two-arm chart](charts/index.html) · [Compact CSV](summary.csv) · [Origin receipts and digests](sources.json)

All methods use the same 127 DS26 and eight DS29 recordings, exact stored native GLRT digests, causal catalogue and supplied original roof tile. The audit checked the four original v5 request and execution receipts for each recording. The chart displays the four original options as a reference range, with the no-repair baseline indicated. Every requested recording remains in the curve and threshold denominators. Median and P95 describe published positions. The paired gate uses the original no-repair error for that recording and calibration arm. The both-arm column counts the intersection of the two per-arm gates.

Each paired entry below gives zero calibration first and fitted calibration second. Threshold counts are inclusive.

| Receiver | Fixes of 135 | ≤1 km | ≤2 km | ≤5 km | Median km | P95 km | Paired 10% | Both arms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Original no repair | 135 / 135 | 72 / 69 | 116 / 115 | 133 / 133 | 0.982 / 0.988 | 2.941 / 2.819 | 135 / 135 | 135 |
| Original selective gap | 135 / 135 | 73 / 70 | 116 / 115 | 133 / 133 | 0.980 / 0.953 | 2.941 / 2.819 | 135 / 135 | 135 |
| Original omitted track one | 135 / 135 | 73 / 70 | 117 / 116 | 133 / 133 | 0.980 / 0.988 | 2.941 / 2.819 | 135 / 135 | 135 |
| Original omitted tracks | 135 / 135 | 74 / 71 | 118 / 117 | 133 / 133 | 0.960 / 0.958 | 2.941 / 2.819 | 135 / 135 | 135 |
| Compact secant | 135 / 135 | 73 / 68 | 116 / 114 | 133 / 133 | 0.977 / 0.989 | 2.936 / 2.817 | 131 / 131 | 131 |
| Native clock + offset OU | 114 / 114 | 38 / 41 | 83 / 83 | 113 / 113 | 1.293 / 1.291 | 3.654 / 3.672 | 37 / 40 | 37 |
| Native agreement cascade, archived routes | 135 / 135 | 72 / 67 | 116 / 114 | 133 / 133 | 0.984 / 1.004 | 2.936 / 2.817 | 130 / 130 | 130 |
| RF preflight, archive replay | 135 / 135 | 72 / 69 | 116 / 115 | 133 / 133 | 0.982 / 0.988 | 2.941 / 2.819 | 135 / 135 | 135 |

The cascade selects one smooth-clock endpoint and 134 matched compact fallbacks under its archived 0.5 km two-arm agreement rule. RF preflight selects saved late-stage outcomes and bypasses the original last search on 16 recordings. The two series represent archived decisions. Compact secant and native clock plus offset OU supply measured replay endpoints. No new receiver fits were run for this comparison. [Cascade evaluation](../cascade/README.md) · [RF preflight evaluation](../late-preflight/README.md) · [OU evaluation](../clock-offset/README.md)

The per-case CSV records publication status, geographic error, conditional frequency RMS, and each paired gate. Conditional RMS describes each method’s retained observation set and can be available for an unpublished fit. The exact published and paired-accuracy recording IDs are provided for both arms. [Per-case scores](scores.csv) · [Paired recording IDs](pairings.json) · [Chart and data seal](roof-lock.json)

```sh
python -m tools.pipeline_eval.qualification.full_receiver_recovery
python -m tools.pipeline_eval figures --panel screening --variant receiver_recovery-roof135 \
  --arm both --out /tmp/receiver-recovery-charts
```
