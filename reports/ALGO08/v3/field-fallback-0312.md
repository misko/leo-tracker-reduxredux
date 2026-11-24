# DS30-0312 proves the repair cap after the first ordinary arm

DS30-0312 entered lean inference on a healthy earlier-orbit census and returned `repair_rejection_cap` before attempting either repair fit. The **first ordinary `c = 0` fit** already supplied enough evidence for that fallback. Its failed curved family and failed predictive track together forced removal of **32 of 563 predictive points**, over the original 5% limit of 28 points. A source-exact short circuit at that point could omit the original exploratory fitted-`c` fit. The complete original two-arm finish took **1.091 s wall / 1.090 s CPU**. That is an upper bound before the cost of the early check. The receipt has no individual arm stopwatch. [Original paired finish](/tmp/leo-v3-integrated-original-batch/reports/ALGO08/v3/blind_joint_finish.py:127) · [Original repair cap](/tmp/leo-v3-integrated-original-batch/reports/ALGO08/v3/blind_joint_repair.py:22)

| Ordinary lean finish | Curved compatible | Predictive compatible | RF RMS |
| --- | ---: | ---: | ---: |
| Fixed `c = 0` | 2,862 / 2,903 | 544 / 563 | 131.082 Hz |
| Fitted `c` | 2,862 / 2,903 | 563 / 563 | 131.007 Hz |

Both arms failed the same 41-point RX1 CH6 T003 curve. It retained the winning branch's NORAD 64376, alias 0, through salvage and the second screen. The fixed arm also failed the 19-point RX2 CH4 T005 predictive entry, NORAD 59676, alias 0. Repair preparation then removed the 13-point RX1 CH7 T009 predictive entry, NORAD 64376, alias 1. Other RX1 upper-band entries survived, establishing loss of the retained curved family as the cause of that extra removal. The original repair summary counted three of 106 total tracks and 41 of 2,903 curved points removed. Those two counts pass the existing cap.

The paired policy requires every curved and applicable predictive gate in both arms. The second arm can only add components to the failed sets. Removing more curves can only reduce surviving family and radio-band support, and adding failed predictive components can only reduce the retained entries. The caps use the fixed original denominators. Consequently the first arm's over-cap count is irreversible at this boundary. The healthy 42 ms router census, first gate, salvage and second screen offered no earlier mandatory rejection. The paired finish starts around 8.642 s into the lean proposal. Its fixed-arm completion time is unavailable. The observed repair preparation spent 4.258 ms and attempted zero refits. [Paired policy](/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3/history_policy.py:169) · [Original support removal](/tmp/leo-v3-integrated-original-batch/reports/ALGO08/v3/blind_joint_repair.py:28)

The frozen veto from DS30-0147 and DS30-0073 requires a **completed repaired** fixed arm, so it has no eligible fit on 0312. DS30-0147's original fixed arm cleared the gates, and DS30-0073's full failed union passed the cap. The recorded controls remain unchanged. The exact nomination handoff also declined on 0312. It excluded the speculative six-node rank and the finalist prefixes before the ordinary seven-node rank. The 2.757 s scout and 3.247 s ordinary rank are already inside separate measured solve scopes. Their counts and recorded refusal supply no reusable whole nomination. [0147 veto](fallback-accounting-0147.md) · [0073 transfer](repair-veto-transfer-0073.md) · [Speculative exclusion rule](combined_successor.py:20)

| Verified scope | Wall s | CPU s |
| --- | ---: | ---: |
| Installed launcher through common verifier | 104.569 | 93.223 |
| Successor launcher through common verifier | 89.770 | 82.857 |
| Successor acquisition | 43.881 | 38.240 |
| Successor solve | 40.154 | 39.881 |
| Abandoned lean proposal, inside solve | 9.737 | 9.672 |
| Ordinary named fallback, inside solve | 27.781 | 27.645 |

The named fallback accepted the successor detector packet and published both arms with 2,988 curved and 559 predictive owners each, 179 grid positions and eight PNGs. Its RF RMS was 132.782 / 132.571 Hz, fixed / fitted. The installed pair used its own full-aperture detector and published 95.988 / 95.926 Hz. The early cap proof leaves the successful named fallback and both published arms intact. Even giving away the whole original two-arm finish leaves **36.394 s** to the **52.285 s** half-time target. Giving away the entire rejected proposal still leaves **27.748 s**. Eliminating both named and lean scopes would only clear half-time by 33 ms and would discard the accepted solution.

The verified generation-1 pair SHA-256 is `ff1af77e320e983c317cf28e4ccc12614fa2effa08c7742e0cd70ce5415fc000`. The successor result SHA is `32d3ebd3f0c8b574823be4e4ccd27e51dceda1f8bffb70a64c9edf0e89230025`, and its signed input and terminal bind the witness `af47a0fa2a1b97a7b8529315382a2196f0e7db3d09e24428a2cdf9b617936cda`. The release marker binds build `30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab`. Both official owner digests were independently reproduced from the witness. This was a metadata audit with no new solver, forecast, receiver, waveform or shared lease.
