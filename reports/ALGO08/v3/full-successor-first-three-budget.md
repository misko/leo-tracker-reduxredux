# Runtime budget on the first three verified DS30 pairs

The first full-length recording, DS30-0178, took **94.459 s** on installed ALGO08v3 and **56.951 s** on the candidate. Reaching half of installed time on this recording requires another **9.722 s**. Acquisition occupied **40.573 s**, including **18.093 s** inside detector callbacks. The position decision and publication took **14.551 s**. The fitted position error increased from **0.387 to 0.605 km**. Both workers verified their complete publications.

| Recording | Installed / candidate (s) | Authenticated acquisition (s) | Detector inside acquisition (s) | Decision and publication (s) | Seconds above half of installed |
|---|---:|---:|---:|---:|---:|
| DS30-0049 | 18.679 / 13.600 | 6.046 | 2.780 | 6.419 | +4.260 |
| DS30-0107 | 2.176 / 0.619 | 0.124 | 0.065 | 0.034 | −0.469 |
| DS30-0178 | 94.459 / 56.951 | 40.573 | 18.093 | 14.551 | +9.722 |
| Sum | 115.314 / 71.170 | 46.743 | 20.938 | 21.004 | +13.513 |

The native detector alone has limited scope on DS30-0049. Even making every callback instantaneous with all other work held constant would leave **1.480 s** to save elsewhere. DS30-0178 has a different cost profile. Holding costs outside acquisition fixed, the **9.722 s** gap would require **24.0%** less time in acquisition. The prefetch thread used **11.039 CPU s** on 92 reads of 7.221 GB. The main thread's recorded demand wait was **2.607 s**. These clocks overlap other acquisition work and cannot be added to it. They warrant checking the read and buffer costs independently.

Both fixes landed farther from the reference with the candidate. DS30-0049 fitted error increased by **2.620 km** and DS30-0178 by **0.219 km**. DS30-0107 withheld on both builds. Across these three, summed speedup was **1.620×** and the reciprocal median paired wall-time ratio was **1.659×**. All three had installed-first launch order. Two were small feasibility cases. The full benchmark includes the opposite launch order and retains all 455 assignments.

Installed ALGO08v3 wrote its authenticated detections **10.945 s** after launch on DS30-0049 and **69.110 s** after launch on DS30-0178. Both exceed half of their respective end-to-end times. The candidate wrote its detections at **7.623 s** and **43.059 s**. Holding these candidate costs constant would leave only **1.717 s** and **4.170 s** for all remaining work to reach 2× on each recording. These observations use the verified detector files’ modification times relative to the worker starts. They include all preceding work and can differ from time inside the receiver.

Each row is bound to its selected attempt and timing witness. Successful timings include independent common publication verification. [Measured stages and provenance](measurements/full-successor-first-three-budget.json) · [Calculator](full_successor_stage_budget.py) · [Full study protocol](full-successor-field-protocol.md)
