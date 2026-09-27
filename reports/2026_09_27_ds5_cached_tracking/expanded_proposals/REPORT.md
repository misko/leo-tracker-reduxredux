# Sparse window transfer fails to recover later-only cases

The unchanged fixed-window diagnostic completed all 318 searches over 106
inactive receiver visits in 45.94 seconds. Sources remained stable and inputs
unchanged. Every inactive receiver was selected, including both receivers on
quiet visits; target selection did not read reference labels. The membership
test passes. No additional holdout was opened.

| Rate | Inactive receiver visits | Seed0 recoveries / extras | Seed5 recoveries / extras | Seed10 recoveries / extras |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 44 | 1 / 0 | 0 / 0 | 0 / 1 |
| 5 MS/s | 62 | 0 / 0 | 0 / 0 | 0 / 0 |

The 5 MS/s cohort has no reference positives, so its zero recoveries say nothing
about sensitivity. Extras are reference-relative unmatched outputs, not proven
physical false alarms. At 2.5 MS/s only visit 1679 RX1 recovers, through seed 0.
Visits 1681, 1688, and 1689 fail the Python proposal margin at all three seed windows;
no native seed or confirmation call is reached for those misses.

Mean complete search CPU per inactive receiver is 70.09/69.67/70.29 ms for
seeds 0/5/10 at 2.5 MS/s and 196.96/194.79/188.13 ms at 5 MS/s. Searching multiple
fixed windows on quiet receivers is expensive and produces no additional
recovery here. These search-only timings exclude primary processing and do not
establish an integrated schedule's speedup. No thresholds or window positions
were retuned after this result.

## A concrete remaining reuse opportunity

Receipt inspection identifies an earlier actual candidate detection on the
same receiver/channel for all three remaining misses: visit 1678, channel 3 RX1.
It establishes a track, but visit 1680 returns negative after guided failure,
clearing it. Visit 1681 and subsequent misses therefore enter cold discovery.
The earlier candidate's second pair member has physical CFO 419536.96 Hz;
scored CFO is 306788.38 Hz, within the supported acquired-frequency domain.
These frequencies are different quantities and must remain separate.

Compared with that earlier measured point, the later reference inventories have:

| Missed visit | Age of prior | Smallest circular timing difference | Physical CFO difference range |
|---|---:|---:|---:|
| 1681 | 0.400816 s | 1.07 us | 1082–1559 Hz |
| 1688 | 1.362742 s | 3.60 us | 4242–4428 Hz |
| 1689 | 1.483130 s | 4.13 us | 4542–4546 Hz |

These are post-hoc reference opportunities, not fresh cache hits, not a
proof every reference pair fits those minima, and not a basis for runtime
reference selection. They support testing a short-lived dormant hypothesis:
clear the accepted track on negative evidence as before, but retain its last
positive timing/frequency only as an expiring proposal for fresh search. Never
renew its lifetime on negatives or copy a stale score into a detection. Every
accepted recovery must pass new receiver-local measurements, tone controls,
pair geometry and physical-frequency consistency, or fall back to discovery.

A bounded timing neighborhood can address drift that simple point reuse
missed, but its whole-call cost must be measured. This experiment remains to
be implemented and tested on both development cohorts and negative/intermittent
controls. It must not be reported as a measured recovery or speedup yet.
