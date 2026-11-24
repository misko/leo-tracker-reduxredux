# The South history packet offers no empty-lane carrier or arrival query

On the original containing South simulation, all **1,700 selected-empty short lanes** lacked a same-piece bracket. The frozen rule issued **zero** carrier or arrival queries. The installed 20 ms packet also had **zero selected positives** on those 1,700 lanes. The transfer therefore provides an eligibility result. Carrier or timing accuracy on South misses remains unmeasured. [Frozen transfer](south-empty-graph-arrival-protocol.md) · [Candidate-only seal](measurements/south-empty-graph-arrival-plan.json.gz) · [Scored result](measurements/south-empty-graph-arrival-score.json).

| Original aperture | Paid lanes | Native positives before history | Kept positives | Truly native empty | Erased by history | Empty after selection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 ms short | 2,096 | 1,276 | 396 | 820 | 880 | 1,700 |
| 20 ms full | 304 | 70 | 60 | 234 | 10 | 244 |

The original signed acquisition and held-selector receipts fix these aperture totals. The selector retained its original history route and ran zero refinements. The retained parent digest identifies the prehistory packet, but the authenticated saved input set omits its per-lane payload. The 820 native empties and 880 history erasures are thus known in aggregate. Individual selected-empty rows cannot be assigned to either category. Neither category supplied a query. The physical DS30 study used the unfiltered short packet, so its per-lane native-empty enrollment does not carry over to the South selected packet. [Original unretimed South input](sparse8-effective-time-south.md) · [Physical empty-Graph enrollment](empty-graph-rescue.md).

The unretimed South Graph reproduced **423 assigned observations, 29 tracks and 15 curved tracks** on 1,200 original stereo visits. Both detector packets matched the signed inventory, admitted opportunities, hardware sample counters, exact RF, and acquisition and delivery clocks. All 1,700 short empties were outside consecutive neighbor brackets in those pieces. The spacing, slope and alias gates had no bracket to evaluate. The unchanged carrier rule and original hardware-counter phase functions produced the following counts. [Original Graph and carrier transfer](track-cfo-denoise.md) · [Frozen joint arrival rule](empty-lane-arrival.md).

| Frequency and arrival window | Carrier only | Joint interpolation | Joint with left phase | Joint with quarter-period shift |
| --- | ---: | ---: | ---: | ---: |
| Primary, ±250 Hz / ±2 samples | 0 | 0 | 0 | 0 |
| Historical tight, ±400 Hz / ±1 sample | 0 | 0 | 0 | 0 |
| Historical loose, ±2,250 Hz / ±6 samples | 0 | 0 | 0 | 0 |
| Wider timing, ±250 Hz / ±128 samples | 0 | 0 | 0 | 0 |

Zero queries also means zero installed-empty queries. Precision, recall and right-neighbor delay have no denominator here. This one simulation supplies no off-site physical generalization. Predictions were sealed before comparing the installed factors at `ca0904218`. Three component and seven adjacent tests passed. The study read saved detector and custody metadata only and ran no receiver, waveform read, ephemeris work, position fit, or benchmark. [Replay harness](south_empty_graph_arrival.py).
