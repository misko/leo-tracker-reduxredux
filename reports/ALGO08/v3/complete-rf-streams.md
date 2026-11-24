# Continuous RF streams restored history support and still lost accuracy

Keeping whole histories at four symmetric RF channels let North publish a fix after the alternating half-duty mask had withheld. The original 20/8 ms history was byte-exact on every continuously paid stream. North nevertheless lost six of nine assigned satellite families and exceeded the 250 m accuracy allowance in both calibration arms. Weak physical DS30-0016 kept its original fixed-zero accuracy but moved the fitted endpoint to **3.040 km** error. Both original containing offers published verified grids, paths and all eight figures. [Frozen policy](complete-rf-streams-protocol.md) · [Saved results and signed receiver ledger](measurements/complete-rf-streams.json.gz)

| Original containing offer | Horizontal error zero / fitted, m | RF RMS zero / fitted, Hz | Assigned observations per arm |
| --- | ---: | ---: | ---: |
| North installed v3 | 105.690 / 140.779 | 5.406 / 5.167 | 302 |
| North all-visit 8 ms | 111.954 / 128.086 | 9.133 / 8.921 | 342 |
| North continuous streams | **1,250.370 / 864.552** | **7.329 / 7.350** | **114** |
| DS30-0016 installed v3 | 1,643.669 / 1,661.443 | 109.375 / 109.479 | 109 |
| DS30-0016 all-visit 8 ms | 490.071 / 980.010 | 134.021 / 133.740 | 115 |
| DS30-0016 continuous streams | **504.029 / 3,040.157** | **134.092 / 133.392** | **92** |

## Paid history and achieved coverage

Pay both radios continuously at channels 1, 4, 5 and 8 within each pilot edge. Every original full anchor remains measured on the other channels. In both recordings the enrolled centres have the same actual midpoint of 11.5846875 GHz and the same 1.75 GHz edge-to-edge interval with or without the short-call selection. Nominal channel variance rises by 19.0%. The recorded factor and owner coverage can differ from those unweighted channel moments. The previous staggered RF experiment kept different chronological thirds, the survey chose an early signal-ranked pair, and the whole-cycle study skipped an entire donor cycle every third cycle. This schedule fixes the alternating trial’s loss of recent paid predecessors on retained RF streams. [Staggered RF](rf-block.md) · [Survey](survey-channels.md) · [Whole-cycle schedule](cycle-stereo-saved.md) · [Alternating half-duty](balanced-stereo.md)

| Signed receiver and selection evidence | North | DS30-0016 |
| --- | ---: | ---: |
| Original issued / admitted stereo visits | 1,200 / 1,200 | 808 / 713 |
| Full anchor lane calls, all measured | 304 | 186 |
| Short lane calls, paid / unmeasured | 1,048 / 1,048 | 678 / 562 |
| Measured positives / measured empty lanes | 812 / 540 | 346 / 518 |
| Paid stereo visits with at least three possible causal predecessors | 588 / 676 | 377 / 432 |
| Original history positives → paid history positives | 456 → 190 | 289 → 201 |
| Original → candidate selected factors | 456 → 190 | 506 → 346 |
| Candidate held gain, radio 0 / 1 nats | +49.702 / +40.199 | −15.326 / −8.832 |
| Candidate selected factors by original visit third | 76 / 76 / 38 | 117 / 108 / 121 |

North again selected history. All 190 selected factors match its original history on channels 1, 4, 5 and 8. On channels with full anchors only, the paid continuation retained no factors. Weak again selected unfiltered. It retained all 74 measured positive full anchors, including available positives on the sparse channels. Its 95 invalid stereo visits have separate `excluded_original` rows. The receipt distinguishes unmeasured rows from measured empty lanes and retains the original clocks and raw authorities. Both arms in each case share one receiver packet.

## Lost owners and calibration

Every surviving observation kept its published NORAD and role in both calibration arms. North lost 228 assigned observations across six complete families. The three retained families each kept both antennas and all 38 assignments over their original 36 s arcs, at channels 1, 4 and 8. The last assigned timestamp moved from 296.220 to 196.132 s even though the scheduler still paid detectors in the final third. North's RF RMS fell by 1.804 / 1.571 Hz against all-visit while horizontal error rose by 1,138.416 / 736.465 m.

Weak kept all 92 conditional owners. The 23 losses were all the channel-3 predictive observations of NORAD 63510. Its channel-4 conditional measurements and time span were unchanged. The other family, NORAD 64015, kept all 43 owners on channel 1. Both assigned families therefore used only one frequency each. This accounts for the removed cross-channel evidence without inferring a location from RF fit. Weak fitted error increased **2,060.147 m** versus all-visit and **1,378.715 m** versus named v3, despite RF RMS close to the all-visit values. Fixed-zero error increased by 13.958 m versus all-visit. The schedule missed the fitted accuracy gate. The owner audit joined every retained owner to its original time, RF and signed factor after both solves sealed. [Read-only audit](complete_rf_streams_score.py)

## Clocks and stop

| Scope | North | DS30-0016 |
| --- | ---: | ---: |
| Saved launch through exit, elapsed / CPU s | 5.350 / 5.291 | 4.873 / 4.841 |
| Numerical solver CPU s | 2.726 | 2.115 |
| Schedule, held selection and sealed staging CPU s | 0.053 | 0.034 |
| Gross omitted native work at original mean, CPU s | 0.929 | 0.451 |
| Estimated native credit after staging, CPU s | 0.876 | 0.417 |

Both workers completed one verified saved handoff, accepted their named signed final fits, and validated 137 and 179 grid points, respectively. Portable catalogue hits were 11 and 19. Each worker reported two major faults and 5,360 and 320 process input blocks, respectively. There were zero waveform calls. The weak saved all-visit comparator used older preparation and ran in 4.516 elapsed s, with 2.438 numerical CPU s. The historical all-visit North numerical scope was 3.345 CPU s inside its complete raw run. The short-call credit is modeled from archived whole-stage CPU and charged call counts. It preserves original acquisition, verification and full anchor costs elsewhere, and does not establish raw through-exit time. Neither candidate earned a raw trial. [North control](eight-ms-native-live.md) · [Weak control](eight-ms-held-fit.md)

Freeze `e3e2cb38a` covers the schedule, scope and both launches. Reproduce with the release Python, checkout `src` ahead of the release on `PYTHONPATH`, and the runner directory plus checkout root on `PYTHONPATH`. As the staged saved reader, run `-Bm reports.ALGO08.v3.complete_rf_streams FRESH_TMPFS_ROOT`, then `-Bm reports.ALGO08.v3.complete_rf_streams_score FRESH_TMPFS_ROOT FRESH_JSON` under the same CPU2 `nice 15` and I/O priority 7 Gauss lock and one numerical thread. The initial scored result hashes to `89160af3023e0913626013e7c8c2747396883e92d7c673e7ad6cefcf87a420e8`. The expanded audited receipt hashes to `201d2a9242da75ae9a58ba1af5c1280b565104ba47f0a24875f5849737c44a44`. [Runner](complete_rf_streams.py) · [Schedule tests](../../../tests/pipeline_eval/test_complete_rf_streams.py) · [Audit test](../../../tests/pipeline_eval/test_complete_rf_streams_score.py)
