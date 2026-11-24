# First-scan 20 ms anchors with 8 ms at every other visit

On the original North waveform, the first-scan anchor kernel saved **0.100 CPU s** versus a fresh two-scan control. The candidate took **11.347 s through exit** versus **10.842 s** for the control. Both produced identical positions, RF residuals, 342 ordered owners per calibration arm, complete numerical evidence and all eight PNGs. The measurements support a cheaper anchor kernel and show no end-to-end improvement in this pair. [Frozen comparison](primary-anchor-8ms-protocol.md) · [Sealed native and publication evidence](measurements/primary-anchor-8ms.json.gz)

## Physical native check

One fully resident original DS30-0016 member supplied all 64 authenticated windows, 58 admitted visits and 116 radio lanes. The independent native first scan matched every rank-zero tuple from the original full call, including fractional epoch, signed CFO, exact score and control score. Both were empty at 55 lanes. The two-scan call supplied a verified rank-one alternate at 24 lanes and no rank-one-only lanes. With the actual mixed schedule on that member, all 16 exported anchor rows and 100 short rows matched the earlier full-anchor 8 ms receiver, and both chose unfiltered at EOF with zero CFO tails. The output detector digest reflects the different measured recipe.

The paired native audit interchanged call order across lanes. Total native CPU for all 116 direct comparisons was **300.573 ms full versus 200.414 ms first**. On the 16 actual anchor lanes it was **48.760 versus 31.238 ms**, a 36% reduction. The instrumented member process took 1.165 s through exit, including both independent audit kernels, and provides no clean acquisition delta. All 19,222 member and index pages remained resident. An initial dispatch error exited before opening any windows or making native calls and cost 0.048 s. [Earlier dense native rank-zero proof](primary-schedule.md) · [Original 8 ms member](eight-ms-native-live.md)

## Full original North pair

The candidate ran first. Both children decoded and verified the same 1,579,423,424 compressed bytes, 1.920 GB decoded and 1,200 original stereo visits, on the same low-priority core. All 385,609 waveform and 188 index pages stayed resident. Both paid 304 anchor and 2,096 short calls. The original 20 ms helper uses the installed first timing scan and verifies against the original samples; it omits the cancellation residual scan. The 8 ms native library, radios, clocks, original operator offer, archive cutoff, EOF selector, 11 portable archive hits, 272 compact ranks and final solver remained matched. Each child performed one acquisition and one verified handoff.

The first-only receiver exported one fewer 20 ms factor. On visit 773, radio 1, the previous maximum-margin measurement was rank one at signed **+244,909.264 Hz**. The native first scan supplied an empty lane. All 2,096 short probes were exact. Held log-score gains were +92.630/+86.133 nats versus +92.630/+83.174 previously. Both chose history and passed the identical 456 ordered detector probes into the solver. This is a concrete difference between matching the full call's rank-zero tuple and preserving the ordinary mixed receiver's strongest factor.

| Scope | First-scan anchor | Two-scan anchor |
| --- | ---: | ---: |
| 20 ms native anchor CPU | 0.745 s | 0.845 s |
| 8 ms native short CPU | 1.987 s | 1.866 s |
| Authenticated acquisition CPU / elapsed | 5.366 / 5.368 s | 5.094 / 5.094 s |
| Numerical solve CPU | 3.441 s | 3.323 s |
| Through exit CPU / elapsed | 11.314 / 11.347 s | 10.838 / 10.842 s |
| Process major faults / input blocks | 70 / 4,352 | 3 / 224 |

The candidate's unchanged short kernel cost 0.121 CPU seconds more, and work outside the two native kernels cost another 0.250 CPU seconds more. The process input counts include work outside the resident waveform and index. One ordered pair cannot isolate the effects of those launch differences. The prior live 8 ms control took 10.828 s. The independently repeated named-v3 reference took 16.133 s and returned the same scientific products as the older named reference. At half of the fresh named clock, the target is 8.066 s. Even a free 0.845 s anchor stage would leave the matched two-scan control above that target. [Named comparison and full acquisition budget](all-visit-physical-budget.md)

Both fresh 20/8 ms runs gave 111.954/128.086 m survey error and 9.133/8.921 Hz RF RMS, ordered `c = 0` then fitted `c`. Named v3 gave 105.690/140.779 m and 5.406/5.167 Hz. Both candidates completed the original geographic check, retained all 342 ordered owner and role assignments per arm, and published the same 137-cell grid and path and eight exact PNGs, each verified at encoded byte and decoded RGBA level. The deliberate receiver recipe change gives the two terminal receipts different native digests. This study measured the containing offer only. The three focused tests passed. [Native adapter](primary_anchor_8ms.py) · [Trial driver](primary_anchor_8ms_trial.py) · [Independent verifier](primary_anchor_8ms_pair_score.py)
