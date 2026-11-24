# Halving short stereo visits cut scientific support

The alternating half-duty schedule kept all full anchors and omitted exactly half the short stereo visits on the two enrolled recordings. North withheld on its original containing offer after the history selector discarded all 838 measured factors. Physical DS30-0016 fixed at **1,504 / 1,538 m** for fixed-zero and fitted calibration, versus **490 / 980 m** on the original all-visit 8 ms route. The smaller weak fit beat the named v3 horizontal errors and failed the preregistered 250 m allowance against the more accurate all-visit control in both arms. [Frozen protocol](balanced-stereo-protocol.md) · [Complete signed plan, results and physical clocks](measurements/balanced-stereo.json.gz)

| Original containing offer | Horizontal error zero / fitted, m | RF RMS zero / fitted, Hz | Owners per arm |
| --- | ---: | ---: | ---: |
| North named v3 | 105.690 / 140.779 | 5.406 / 5.167 | 302 |
| North all-visit 8 ms | 111.954 / 128.086 | 9.133 / 8.921 | 342 |
| North alternating half | Withheld | — | 0 |
| DS30-0016 named v3 | 1,643.669 / 1,661.443 | 109.375 / 109.479 | 109 |
| DS30-0016 all-visit 8 ms | 490.071 / 980.010 | 134.021 / 133.740 | 115 |
| DS30-0016 alternating half | **1,504.022 / 1,538.458** | **114.900 / 114.244** | **64** |

Weak error rose **1,013.951 / 558.448 m** against all-visit while RF RMS fell **19.121 / 19.496 Hz**. The new result kept 64 of 115 ordered original owner IDs and made no NORAD or role changes among them. The existing orbit path used 19 portable body hits and 48 compact rank profiles. It evaluated 25 original-region probes and accepted the named final fit, with both calibration arms, the 179-point grid, path, and all eight verified decoded images. The physical all-visit accuracy is the earlier saved control, using older preparation options. [Controls](whole-stereo-8ms.md) · [North raw all-visit control](eight-ms-native-live.md)

## Balanced coverage and why North withheld

The policy alternates between three and four paid shorts per anchor cycle, with opposite phase on adjacent RF channels. Unlike the earlier two-of-three individual mask and the whole-cycle mask, it omits half and leaves at most one consecutive omitted slot within each admitted stream. Both recordings still cover all eight original RF streams and their late capture tails. Per-stream short omission was 49.62–50.38% on North and 49.23–51.16% on weak. Maximum same-stream gap grew from 2 to 4 s on North and from 1.419 to 1.774 s on weak. The longest shrinkage of a stream's first-to-last paid span was 2 s and 0.355 s, respectively. [Two-of-three control](whole-stereo-8ms.md) · [Whole-cycle control](cycle-stereo-saved.md) · [Predecessor-only span audit](span-sweep-schedule.md)

| Signed receiver scope | North | Physical DS30-0016 |
| --- | ---: | ---: |
| Issued / originally valid stereo visits | 1,200 / 1,200 | 808 / 713 |
| Full anchor lane calls, all measured | 304 | 186 |
| Short lane calls, paid / unmeasured | 1,048 / 1,048 | 620 / 620 |
| Measured positives / measured empty lanes | 838 / 514 | 285 / 521 |
| Original → candidate selected factors | 456 → **0** | 506 → **285** |
| Original → candidate held-route choice | History → history | Unfiltered → unfiltered |
| Original → candidate held gain, radio 0 / 1 nats | +92.630 / +83.174 → **+36.376 / +29.022** | −25.287 / −11.749 → **−36.174 / −14.254** |

North had 144 complete held cycles per radio, with 39 positive held anchors on each. The three/four paid-donor likelihood uses only measured donor opportunities. That correction leaves a predictor with no history votes but strong negative-anchor predictions. It wins the relative likelihood on these mostly negative held labels. The chronological output has a separate necessary condition of at least three earlier nonempty groups in the last 12 same-lane opportunities and within eight seconds. Among **all 676 paid North stereo visits**, the number of scheduled paid predecessors in that window was zero at 8 visits, one at 8 and two at 660. Even an all-positive receiver could never satisfy the original vote minimum here. A paid-only queue with the same time window still sees at most two. This bound uses clocks and paid flags before CFO and candidate results. The actual selected history had zero factors, both terminal arms empty, no grid or path, and zero images. The sealed reason was `no_active_curvature`. Weak kept all 74 measured positive full-anchor factors via its chosen unfiltered route. The 95 excluded original stereo visits retain a separate state. [Signed event ledger and support histograms](measurements/balanced-stereo.json.gz) · [Original three-vote rule](../../../tools/pipeline_eval/variants/carrier_continuation.py)

## Measured saved costs and original receiver estimate

| Timing scope | North | DS30-0016 |
| --- | ---: | ---: |
| Schedule, signed events, selection and native handoff seal CPU | 0.048 s | 0.030 s |
| Saved worker through exit, elapsed / CPU | 0.789 / 0.787 s | 4.296 / 4.285 s |
| Numerical solve CPU | None | 2.116 s |
| Original short stage mean-based gross credit | 0.929 s | 0.498 s |
| Credit after charged planning | 0.881 s | 0.468 s |

North's short process reflects loss of the fix. The historical weak all-visit saved control took 4.516 s elapsed and 2.438 numerical CPU s; its preparation options differ. The observed new 2.116 numerical seconds give a bounded saved-fit change with the degraded evidence. The estimated input credits use original short CPU and leave all full anchors, source verification and other acquisition charged. Per-lane native timing, raw through-exit time and retry savings are unmeasured for this schedule. [Original weak saved clocks](eight-ms-held-fit.md)

The case order, selector and mask were committed at `763283b9a` before reading the signed staged detector outcomes. Both paid launches ran once under the shared Gauss lock, CPU2, nice 15, I/O priority 7 and one numerical thread. They used one staged native handoff each and zero waveform calls. The parent initially picked the installed storage accessor for post-run verification, which lacks its checkout's read-only option. A verification-only recovery put checkout `src` first on `PYTHONPATH` and retained the successful North child as run, then launched the scheduled weak child. The receipt expands to SHA-256 `22c5609434e77e5fe73b3f0a0698f91002458945dcf34e110753407f28103701`. [Runner](balanced_stereo.py) · [Tests](../../../tests/pipeline_eval/test_balanced_stereo.py)
