# Rolling tracker with bounded backward extension

The prototype recovers all four targeted long segments (#12, #48, #51, #52).
On the frozen ARM GLRT observations from the 300-second DS9 scan, reviewed
server-segment agreement improves from 39/62 to 47/62, with no previous
matches lost. Physical PLUTO+ reconstruction takes 2.55621 seconds versus
1.11931 seconds for the original rolling tracker: **128.4% more time**, so
the proposed <=20% overhead target **fails**.

| Method, using ARM GLRT observations | Short <15 s | Medium 15–30 s | Long >=30 s | Total | PLUTO+ tracking |
|---|---:|---:|---:|---:|---:|
| Frozen rolling linear | 3/9 | 17/25 | 19/28 | 39/62 (62.9%) | 1.119 s |
| Rolling + bounded backfill | 3/9 | 21/25 | 23/28 | 47/62 (75.8%) | 2.556 s |
| Prior coarse-seeded curvature comparison | 3/9 | 23/25 | 23/28 | 49/62 (79.0%) | 3.543 s |

Times cover tracking from saved GLRT observations, excluding GLRT computation,
RF acquisition, association, and positioning. Coarse-seeded time includes both
of its tracking stages. Baseline/comparison times are frozen prior physical
measurements on the same PLUTO+; backfill is newly measured on 192.168.1.15.
This is one recording, not a cross-recording generalization claim.

| Target reference | Original matching sources | Backfill matching sources | Backfill in-span purity | Meets unchanged criterion |
|---|---:|---:|---:|---|
| #12 | 64/86 (74.4%) | 69/86 (80.2%) | 100.0% | Yes |
| #48 | 43/54 (79.6%) | 48/54 (88.9%) | 92.3% | Yes |
| #51 | 45/59 (76.3%) | 59/59 (100%) | 92.2% | Yes |
| #52 | 46/68 (67.6%) | 68/68 (100%) | 97.1% | Yes |

Backfill recovers all available matching ARM sources for these four references;
it cannot restore reference detections absent from the ARM GLRT input.
ARM gains are #9, #12, #21, #22, #39, #48, #51, #52. On server GLRT input,
agreement rises from 58/62 to 61/62, gaining #9, #23, #35 with no losses.
Hypothesis counts remain 327 on ARM input and 407 on server input. These
overlapping hypotheses are not 327 distinct satellites.

| Additional check | Result |
|---|---|
| Physical ARM-input tracking repetitions | 2.56147 / 2.55621 / 2.55309 s |
| Physical whole-process median, including parsing/output | 3.62530 s |
| Maximum resident memory | 11,488 KiB |
| Physical server-input tracking, one run | 3.01610 s |
| Host tracking medians, ARM / server input | 0.06163 / 0.07134 s |
| Host repetition determinism | All three repetitions identical on both inputs |
| Physical output versus host | All four runs byte-identical |
| Component tests | Host, ASan/UBSan, and physical ARM unit tests pass |
| Known synthetic curves | 2/2 recovered; each 117/117 points; purities 100% and 98.3% |
| ARM local prediction residual p95 | 486.3 Hz before, 459.4 Hz after |

## Implementation and limits

The forward rolling tracker is preserved. For each surviving hypothesis,
the prototype identifies its first confirmation (8 sources spanning 4 s),
then walks backward through at most 16 s of earlier evidence within a 32 s
history interval. It refits an 8 s / 32-point local linear model at each step,
using the existing alias-aware residual, gap, and rate limits. It greedily
retains one backward association. Identical confirmation states share cached
extensions. Reference track labels are used only by evaluation.

Review corrected confirmation-prefix source exclusion, cache state identity,
source-group atomicity, fit-point limits, actual-time gap/chronology checks,
and finite bounded configuration validation. Source groups must span <=20 ms.
The original forward tracker and golden scientific fixtures were not changed.

This is an **offline post-pass replay prototype**, not a qualified live
bounded-memory service. Backfill decisions use confirmation-visible evidence,
but the prototype runs over eventual surviving forward hypotheses. Finished
output cardinality is not bounded by the 24-active-hypothesis limit, and the
post-pass still scans the full input for each uncached extension. Those scans
and string-based lookup/bookkeeping are candidates for profiling and
optimization; no measured speedup from such future changes is claimed.
The next implementation step should move extension to the actual confirmation
event and use an indexed lane history, preserving these replay results.

The tracking-only 2.56 s cost is small relative to a 300 s scan, but this does
not establish real-time acquisition plus GLRT plus tracking or worst-case
latency under continuous adaptive scanning. No RF collection, firmware
modification, or production activation was performed for this experiment.

## Evaluation and evidence

The shared evaluator and frozen matching thresholds are unchanged: exact
lane, same source, alias-aware CFO agreement within 2.5 kHz, >=80% reference
source coverage, and >=80% in-span output purity. Only the previously approved
ref #10 exception is excluded, giving 62 eligible references. Ref #35 remains
included. Agreement with server assignment is not satellite identity truth.

- [Protocol](protocol.md), [machine-readable summary](summary.json)
- [Component implementation notes](component/README.md), [review](review/streaming-rolling-backfill-review.md)
- [Host qualification](../2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/receipt.json)
- [Physical qualification](../2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/device/receipt.json)
- [Full ARM evaluation](../2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/arm-evaluation.json)
- [Full server evaluation](../2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/server-evaluation.json)
- [Target comparison PNG](target-comparison.png), [PDF](target-comparison.pdf)

`summarize.py` and `plot_targets.py` regenerate the summary and plots from the
saved qualification results. `MANIFEST.sha256` binds final report/source and
qualification artifacts; exploratory component files are separate from the
final qualification receipts.
