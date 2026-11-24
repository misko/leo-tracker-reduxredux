# Earlier-orbit dispatch preserves the physical DS30-0016 20/8 ms fix

The integrated raw CLI's solver handoff on saved physical DS30-0016 detections exited in **5.690 s elapsed / 5.624 CPU s**. It chose lean discovery and accepted the original signed fit in both arms. The signed terminal, all 115 ordered owners and roles per arm, recorded path and eight encoded and decoded PNGs reproduced the earlier exact named publication on the same 20/8 ms packet. All ordered coordinates, scores and failures matched across the 179-point standard grid. Only its `elapsed_seconds` differed. [Frozen protocol](history-risk-weak-physical-protocol.md) · [Sealed physical comparison](measurements/history-risk-weak-physical.json.gz)

| Physical DS30-0016 reference | Fixed-zero error | Fitted error | Conditional RF RMS, fixed / fitted | Owners per arm |
| --- | ---: | ---: | ---: | ---: |
| Installed v3, original full-20 receiver | 1,643.669 m | 1,661.443 m | 109.375 / 109.479 Hz | 109 |
| Earlier exact named solve, same 20/8 packet | 490.071 m | 980.010 m | 134.021 / 133.740 Hz | 115 |
| Current routed solve, same 20/8 packet | 490.071 m | 980.010 m | 134.021 / 133.740 Hz | 115 |

On its own authenticated 20/8 measurements, the dispatched solver kept all 92 conditional and 23 predictive owners, with no satellite or role change against the exact 20/8 comparison. The original full-20 benchmark provides independent owner counts and digests. The 20/8 result reduced site-reference error by **1,153.597 m** fixed and **681.432 m** fitted while conditional RF RMS increased in both arms. Within the 20/8 result, fitting `c` reduced conditional RF RMS by 0.282 Hz and increased horizontal error by 489.939 m. The publication's all-owner plot RMS was separately 135.547 and 136.859 Hz. The site reference comes from the recording's operator-site authority audit. [Exact same-packet control](named-weak-all8.md) · [Original full-20 signed benchmark](raw-0016-best.md)

The launch regenerated the exact original held packet using the raw entry's EOF adapter on the authenticated, complete unfiltered archive packet `f16ca1c6…`. The 808 issued visits included 713 admitted stereo visits, 1,426 original radio lanes and 506 signed factors. Both held radio scores favored unfiltered chronology, by 25.287 and 11.749 nats. Every measurement survived with zero CFO-tail calls. The new selected bytes reproduced `aeb4658b…` and its original detector recipe, opportunity ledger, inventory and raw recording authority. The physical offer and distinct screen center were passed through unchanged at cutoff `1794568912154038024`. The original early graph proof did not withhold. Its longest lane spanned 35.435 s.

The one shared preparation paid for a fresh source index from 46 resident causal snapshots with 20 distinct bodies. No portable artifact was loaded. Both earlier catalogues had 1,449 eligible rows and zero unusable samples at the declared knots. The census charged 30.895 CPU ms. The actual late terminal check ran on the accepted pair, found both estimates inside the bounds and ran zero exterior probes. There was no numerical retry or fallback.

| Timing scope | Elapsed / CPU s |
| --- | ---: |
| Fresh saved worker through verified exit | 5.690 / 5.624 |
| Numerical solve, including preparation and grid | 2.481 / 2.447 |
| Shared cold numerical preparation, inside solve | 1.584 / 1.584 |
| Original eight-figure renderer | 1.457 / 1.457 |
| Launcher admission, including EOF regeneration | 0.306 / 0.288 |
| Detector receipt verification and regeneration, inside admission | 0.054 / 0.054 |
| Archived exact named, same saved packet and portable index | 6.453 / 6.434 |
| Archived deployed v3, original waveform through exit | 10.824 / 10.816 |

The new run measures the saved handoff on physical receiver data. The historical deployed row starts from its own original waveform. The same-packet archived saved row uses an earlier portable index and comes from a separate process. The new measurement opened no original waveform or backing archive. Its process counters recorded eight major faults and 16,976 input blocks, without attributing them to particular files.

Run [the saved transfer driver](history_risk_weak_physical.py) under the shared low-priority CPU 2 lock with the release Python and one numerical thread. The first admission stopped before launching a worker because the archive writes radio keys as JSON strings. Comparing the original canonical JSON proved exact held-score equality. The one paid worker exited zero on the next admission. Its read-only scorer subsequently needed the existing repository qualification path. No solve was repeated. Fourteen component and adjacent tests passed.
