# Full receivers on the original 135-roof panel

Compact five-refresh secant retained all 135 roof fixes and matched the original v5 5 km coverage exactly. Native smooth clock, curve anchors, and adaptive phase support were measured from the same stored native GLRT factors and published fewer fixes. The standard chart shows the baseline curve and the envelope of the four original v5 options. The table, [per-record scores](scores.csv), and [all pairwise crossings](crossings.json) retain each option separately. [Both-arm figure book](charts/index.html).

Each row has 135 offers, comprising 127 DS26 and eight DS29 recordings. The audit authenticated the four archived v5 executions per recording and checked exact native GLRT, causal catalogue, and original tile bindings for all four new receiver paths. The three native workers also attest identical anonymous Graph projections to the sealed native joint control. Scoring used the frozen truth after the receiver runs. The chart and counts use published positions, with withholding counted against the full offered denominator. Median and P95 use published fixes. [Evidence sources](sources.json), [figure seal](roof-lock.json).

| Receiver or archived v5 option | `c=0` published / ≤5 km | `c=0` median / P95 km | Fitted `c` published / ≤5 km | Fitted `c` median / P95 km |
| --- | ---: | ---: | ---: | ---: |
| Original v5 baseline | 135 / 133 | 0.982 / 2.941 | 135 / 133 | 0.988 / 2.819 |
| Original v5 selective gap | 135 / 133 | 0.980 / 2.941 | 135 / 133 | 0.953 / 2.819 |
| Original v5 one omitted track | 135 / 133 | 0.980 / 2.941 | 135 / 133 | 0.988 / 2.819 |
| Original v5 omitted tracks | 135 / 133 | 0.960 / 2.941 | 135 / 133 | 0.958 / 2.819 |
| Compact v5 secant | 135 / 133 | 0.977 / 2.936 | 135 / 133 | 0.989 / 2.817 |
| Native smooth clock | 119 / 114 | 1.530 / 4.463 | 119 / 115 | 1.284 / 4.751 |
| Native curve anchors | 108 / 103 | 1.800 / 4.810 | 108 / 104 | 1.579 / 4.530 |
| Native adaptive phase | 90 / 87 | 1.600 / 4.317 | 90 / 86 | 1.383 / 4.063 |

Compact secant was at or below 1.05× the original baseline error on 129/135 recordings and at or below 1.10× on 131/135 in each arm. The four original v5 options and compact secant shared the same 133 within 5 km. For all three native receivers, DS26-0203 was the only addition to the baseline’s within-5-km set. At `c=0`, smooth clock, curve anchors and adaptive phase lost 20, 31 and 47 of the baseline’s within-5-km recordings, respectively. With fitted `c` the losses were 19, 30 and 48. Across the complete panel, the baseline CDF never trailed any of the three native curves. The crossing file records all 168 pairwise comparisons across both arms and the combined, DS26, and DS29 groups. It gives strict CDF lead intervals and the shared and exclusive recording IDs for publication, 5 km, and the two per-record relative tolerances. [Summary by dataset and arm](summary.json), [crossings](crossings.json).

## Frequency and timing

Median conditional RMS in Hz for `c=0` / fitted `c` was 109.78 / 98.15 for the original baseline, 71.17 / 71.05 for compact secant, 151.72 / 126.03 for smooth clock, 146.53 / 120.50 for anchors, and 203.77 / 186.13 for adaptive phase. Each value uses the method’s selected observations. It should be read alongside the coverage and geographic results above.

Compact secant replayed complete stored native factors through the full compact v5 cavity workflow with all five initial refreshes. Its 129.88 s median worker wall time covers the 121 fresh roof jobs. Six timing and eight confirmation positions are reused from separately sealed runs and contribute to accuracy. The original baseline’s 417.42 s archived median comes from its own run schedule. The three native paths replayed the full stored factors, rebuilt the anonymous Graph, and solved both arms in a capped host worker. Their per-roof-run median wall times were 6.03 s for smooth clock, 3.55 s for anchors, and 6.45 s for adaptive phase. These are independent stored-factor run schedules. Detector acquisition from raw IQ and board timing are outside the measured boundaries. [Execution receipts](sources.json).

```sh
python -m tools.pipeline_eval.qualification.full_receiver_refinement
python -m tools.pipeline_eval figures --panel screening --variant full-receiver-refinement-roof135 --arm both --out /tmp/full-receiver-refinement-charts
```
