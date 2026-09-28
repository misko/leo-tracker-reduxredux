# Joint mixture feasibility results

Lower composite predictive NLL per evaluation block is better. These are fixed-site retrospective comparisons, not new location estimates. See PROTOCOL.md for model assumptions and limitations.

| UTC | Block noise (Hz) | Site | Frozen IDs, no clock | Joint IDs, no clock | Joint IDs + clock | Null tracks (posterior mean %) | Chain score spread |
|---|---:|---|---:|---:|---:|---:|---:|
| 07:00 | 100.0 | reference | 11.6392 | 7.4433 | 7.4247 | 1.7 | 0.0198 |
| 07:00 | 100.0 | sacramento | 11.6076 | 7.5665 | 7.5502 | 1.7 | 0.0166 |
| 07:00 | 100.0 | reno | 12.7433 | 7.4824 | 7.4634 | 1.7 | 0.0200 |
| 07:00 | 200.0 | reference | 7.7749 | 6.7209 | 6.7175 | 0.0 | 0.0045 |
| 07:00 | 200.0 | sacramento | 7.7680 | 6.7548 | 6.7516 | 0.0 | 0.0041 |
| 07:00 | 200.0 | reno | 8.0518 | 6.7313 | 6.7275 | 0.0 | 0.0052 |
| 08:10 | 100.0 | reference | 7.2260 | 6.7133 | 6.6665 | 0.0 | 0.0512 |
| 08:10 | 100.0 | sacramento | 6.6010 | 6.4241 | 6.4232 | 0.0 | 0.0009 |
| 08:10 | 100.0 | reno | 11.4327 | 7.1686 | 7.1676 | 0.0 | 0.0024 |
| 08:10 | 200.0 | reference | 6.6761 | 6.5540 | 6.5538 | 0.0 | 0.0000 |
| 08:10 | 200.0 | sacramento | 6.5192 | 6.4860 | 6.4832 | 0.0 | 0.0002 |
| 08:10 | 200.0 | reno | 7.7213 | 6.6575 | 6.6581 | 0.0 | 0.0013 |
| 10:30 | 100.0 | reference | 6.7274 | 6.0069 | 5.9990 | 0.0 | 0.0102 |
| 10:30 | 100.0 | sacramento | 7.5707 | 6.3005 | 6.2999 | 0.0 | 0.0004 |
| 10:30 | 100.0 | reno | 8.2813 | 6.6512 | 6.6405 | 0.0 | 0.0221 |
| 10:30 | 200.0 | reference | 6.5499 | 6.3800 | 6.3765 | 0.0 | 0.0018 |
| 10:30 | 200.0 | sacramento | 6.7702 | 6.4681 | 6.4624 | 0.0 | 0.0053 |
| 10:30 | 200.0 | reno | 6.9440 | 6.5498 | 6.5405 | 0.0 | 0.0025 |

## Inference and approximation checks

| UTC | Max omitted historical prior mass (%) | Shared train/evaluation second bins | Max assignment TV between chains |
|---|---:|---:|---:|
| 07:00 | 2.65 | 415 | 1.000 |
| 08:10 | 5.23 | 235 | 1.000 |
| 10:30 | 2.65 | 299 | 1.000 |

A total-variation distance of 1 means the chains assigned some track to disjoint sets of hypotheses in retained draws. This is evidence of inadequate exploration for that track, not proof of calibrated ambiguity. The zero-clock joint arm has only one chain and weaker diagnostics. None of these runs should be promoted as a converged posterior without improved exploration and additional checks.

Settings were fixed before inspecting these scores. No best noise setting is selected. Report all arms, including unfavorable rankings.
