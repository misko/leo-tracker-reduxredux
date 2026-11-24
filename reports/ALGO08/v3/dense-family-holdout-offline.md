# Offline held-RF family prediction

On DS30-0008 the fixed-center, training-only model preferred 63478 over 67511 by **19.036 nats** with `c = 0` and **1.528 nats** with fitted `c`. RX2 favored the other family in both arms. On the independent DS30-0057 fold, relative scores favored its training-selected family 66338 over 53836. Even 66338 scored below the training-calibrated pure-clutter baseline. This pair provides limited support for using the held rank as a family selector. [Frozen protocol](dense-family-holdout-offline-protocol.md) · [Complete forecasts and score receipts](measurements/dense-family-holdout-offline.json.gz)

Each worker prepared the seven training RFs once. The worker reproduced the earlier blind nominations at the actual offer center and retained that training context through noise estimation, history qualification and nuisance fitting. Both alternatives shared the same training arcs, prior model, powers and three phase linearizations. DS30-0008 used six mutually nominated arcs among 85 training arcs with 3,879 points. DS30-0057 used the 64-point training arc that nominated its independent pair, among 29 arcs with 1,031 points. Training radio settings and phase came from the seven RFs alone. The only held inputs available to the forecaster were opportunity identities, clocks, radio and RF. The wrapped-frequency predictions were sealed before a separate scorer reopened the authenticated native files.

| Held case and first rival | Calibration | First minus second (nats) | RX1 (nats) | RX2 (nats) | First vs clutter (nats) | Second vs clutter (nats) |
|---|---|---:|---:|---:|---:|---:|
| DS30-0008, 63478 | `c = 0` | +19.036 | +38.132 | −19.095 | +660.539 | +641.503 |
| DS30-0008, 63478 | Fitted `c` | +1.528 | +3.547 | −2.019 | +687.269 | +685.740 |
| DS30-0057, 66338 | `c = 0` | +122.146 | +128.444 | −6.298 | −47.363 | −169.509 |
| DS30-0057, 66338 | Fitted `c` | +116.956 | +125.663 | −8.707 | −50.143 | −167.099 |

The score included 784 positive and 910 empty opportunities on DS30-0008, and 367 positive and 303 empty opportunities on DS30-0057. The alternatives had the same visible signal scope in each case, so empties contributed equally to the pair contrast. They still affected comparison against clutter. The pure-clutter scores were −10,879.494 and −5,007.794 nats, computed from the sealed radio clutter rates and exact held positive counts with a uniform density over one native period. The dense rival split changed sign by time block. The independent RX1 preference concentrated between 60 and 80 seconds. Raw training residual RMS was approximately 13.2 kHz and 8.0 kHz, respectively, under the robust fixed-center models. These scores characterize the frozen forecasts with their modeled clutter choice and conditional posterior variance. The receiver and time-block results bound the evidence for a stable preference. This offline score did not evaluate horizontal error.

## Measured compute and memory

| Boundary | DS30-0008 CPU / elapsed (s) | DS30-0057 CPU / elapsed (s) |
|---|---:|---:|
| Training preparation and nominal shortlist | 8.466 / 8.468 | 2.725 / 2.726 |
| Training-only history, noise and design setup | 4.628 / 4.631 | 2.207 / 2.207 |
| Four fixed-center fits and forecast creation | 1.170 / 1.177 | 0.122 / 0.122 |
| Cold producer including seal | 14.486 / 14.500 | 5.254 / 5.255 |
| First score using the forecast | 0.635 / 0.637 | 0.621 / 0.623 |
| Repeat score using the same forecast | 0.072 / 0.072 | 0.012 / 0.012 |
| Cold producer plus first score | 15.121 / 15.137 | 5.875 / 5.878 |
| Earlier complete saved solve through publication | 27.693 / 27.699 | 9.862 / 10.011 |

The preparation clock includes binding, the seven-RF Graph, the causal bank at the actual offer center and independent nomination. Both training passes fit inside the offline 45-second case timeout. Together the cold producer and first scorer consumed **20.996 CPU s**, above the earlier 8-second research gate. The first and repeat score exactly agreed. Those replay times include authenticated held packet and forecast reads and exclude the cold producer. The JSON caches retain 517,413 and 206,192 bytes. The training workers peaked at 1,701,828 and 873,072 KiB RSS. The compact replay peaked at 180,036 and 151,180 KiB respectively. The retained train time/CFO arrays of the fitted arcs alone account for 62,064 and 16,496 bytes in memory. Overall training RSS includes the causal bank, conversion copies and full graph. The saved comparison uses a separate earlier process and end-to-end publication clock.

The study demonstrates reuse of a sealed seven-RF forecast. It gives no measured speed credit for a second full solve or for sharing an orbit screen from a different center. Candidate assessment for a live pipeline would still pay its own cold training and memory costs until a shared exact route is measured. Zero raw waveform reads, position fits and public figures ran. Eight focused component tests passed. [Runner](dense_family_offline.py) · [Tests](../../../tests/pipeline_eval/test_dense_family_offline.py) · [Dense saved comparison](dense-8ms-prefix.md) · [Transfer saved comparison](exact-solver-0057.md)
