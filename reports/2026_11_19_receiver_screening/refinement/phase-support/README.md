# Causal orbit-phase support in the blind native joint receiver

The history-adaptive bound recovered a real wider phase in DS26-0223 and changed which satellites explained anonymous tracks. Across all 135 correctly supplied roof tiles it removed 29 net publications in each calibration arm. The fixed ±7.5 s receiver is the better default on this evidence. Both receivers withheld all nine true omitted offers.

The receiver used complete frozen native GLRT factors to build the original Graph. The only scientific change was the orbital phase prior and associated support. The candidate compared the original catalogue element with the closest distinct earlier element available in the frozen request, propagating both to the same recording epoch. It projected their TEME position difference onto the current velocity, converted that displacement to seconds, and scaled it by the ratio of current element age to the gap between element epochs. A 1 s floor was added in quadrature, the width was clamped to 2.5–7.5 s, and the bound was three widths. This is a prediction-disagreement proxy. Each element predates its authenticated snapshot collection, which precedes the recording cutoff. Orbits without a valid pair keep the fixed prior.

The same per-orbit width and bound set the phase shapes used in track shortlisting, shared-orbit pair and bucket fitting, held predictions, training and final position fits, and the exact orbital objective. The interpolation grid covers the entire ±22.5 s support at both ends. GLRT points, Graph construction, available orbit IDs, tile, alias choices, gate, and search budgets stayed fixed. The two calibration arms used the same method-specific assignment. Inference received no archived v5 fit, satellite ownership, or receiver truth. [Frozen protocol](PROTOCOL.md), [plan and source hashes](plan.json), [prediction seal](prediction-lock.json).

## Geography

| Roof measure, 135 recordings | Fixed `c=0` | Causal `c=0` | Fixed fitted `c` | Causal fitted `c` |
| --- | ---: | ---: | ---: | ---: |
| Published | 119 | 90 | 119 | 90 |
| Published within 5 km | 114 | 87 | 114 | 86 |
| Published error median / P95, km | 1.759 / 4.695 | 1.600 / 4.317 | 1.584 / 4.723 | 1.383 / 4.063 |
| Forced error median / P95, km | 1.803 / 5.044 | 2.108 / 9.556 | 1.630 / 4.980 | 1.960 / 9.581 |

In each arm 86 recordings published under both policies, 33 lost publication, and four gained it. Median paired error change among the 86 was +0.003 km at `c=0` and +0.005 km with fitted `c`. The smaller candidate publication medians accompany the reduced denominator. Both policies published three of the four hash-selected confirmations DS26-0207, DS26-0040, DS26-0080, and DS26-0026. Their median forced error rose 2.047→2.507 km at `c=0` and 1.800→2.173 km with fitted `c`. The universal-width diagnostic withheld both of its genuine omitted offers. [All scores](scores.json), [roof plots](charts/index.html).

### Disputed recordings

The errors below are the actual unconstrained-by-publication endpoint errors in km, including withheld positions. Each cell is `c=0` / fitted `c`. Publication applies to both arms in these cases. The universal policy used a 7.5 s prior and ±22.5 s everywhere.

| Recording | Fixed | Causal | Universal wide |
| --- | --- | --- | --- |
| DS26-0223 | 1.635 / 1.832 withheld | 6.639 / 6.754 published | 6.228 / 6.351 withheld |
| DS26-0197 | 1.884 / 1.189 withheld | 2.369 / 2.673 withheld | 2.618 / 2.905 withheld |
| DS29-0316 | 2.620 / 2.494 withheld | 9.573 / 9.656 withheld | 5.872 / 5.960 published |
| DS26-0036 | 1.833 / 1.016 published | 5.220 / 4.546 withheld | 5.228 / 4.511 withheld |

In DS26-0223 the causal pair supplied ±22.5 s for NORAD 67315. The blind fit assigned it a 57-point track at −10.529 s. The universal-wide control also selected that track with the same orbit at −10.469 s. Relative to the fixed receiver, the causal run changed the satellites of five of 135 common tracks and admitted four additional tracks. The extra support therefore reached the assignment machinery, while the full-capture RF and geography deteriorated. Other disputed cases changed six to sixteen common-track owners. [Track identities and deltas](owner-deltas.json).

## Frequency and resource costs

On the roof panel, the median conditional residual RMS rose from 182.56 to 203.77 Hz at `c=0` and from 159.23 to 186.13 Hz with fitted `c`. These residuals use each method’s own selected tracks and satellites. The median support moved from 3,696 to 3,759 points. In DS26-0223, the fixed-to-causal RMS rose 191.3→439.5 Hz and 178.8→437.6 Hz. Comparing policies combines fit and track-selection effects. Within each policy the two calibration arms use matched tracks and owners.

Across 144 causal runs, history processing added a median 0.400 CPU seconds and 0.411 wall seconds. It read a median 57.0 MB of authenticated snapshot text, retained 134,470 bytes of earlier TLE lines for paired orbits, and formed a 7,708-byte numeric width port. There were a median 960.5 valid pairs, 1,921 propagated element states, 505 widened orbits and two fallback orbits. Complete candidate wall median was 6.457 s, versus 5.353 s for the prior stock panel under a different worker schedule. Four contemporary fixed runs reproduced the sealed stock endpoints exactly in both arms. Maximum observed candidate worker RSS was 156,644 KiB under the inherited 512 MiB address-space cap. This measurement begins at saved complete native factors on a Linux host. [Resource receipts](scores.json).

## Reproduction

The sealed run includes 135 causal roof jobs, nine causal omitted jobs, four fresh fixed jobs, and six universal-wide jobs. The initial launcher missed an omitted-only recording in its roof lookup. Two outstanding jobs were resumed using the same frozen worker and request paths before the 154 predictions were sealed and scored. The replay wrapper resolves that lookup before scheduling and writes its independent seal under the supplied scratch directory. The final two commands score and render the published seal.

```sh
python -m tools.pipeline_eval.qualification.phase_support_replay /tmp/phase-support-replay --full --seconds 450
python -m tools.pipeline_eval.qualification.phase_support_results
python -m tools.pipeline_eval figures --panel screening --variant phase_support_roof --variant phase_support_omitted --arm both --out /tmp/phase-support-figures
```

[Run receipt](run-receipt.json), [rendering inputs](figures.json), [roof lock](roof-figure-lock.json), [omitted-offer lock](omitted-figure-lock.json).
