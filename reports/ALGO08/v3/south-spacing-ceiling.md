# Passing South spacing admits 39 edits and restores zero matches

Giving every archived spacing failure a perfect pass enabled **39 distinct CFO edits** across **23 stereo visits** on the public South simulation. All 39 already matched the archived installed winner in both the strict and loose windows. The edits restored zero matches and spoiled zero. On this fixed history-selected packet and Graph, relaxing spacing alone could reach at most **39 of 228 held candidate positives (17.1%)**, or 3.25% of all 1,200 held radio lanes. [Frozen protocol](south-spacing-ceiling-protocol.md) · [Candidate-only bracket seal](measurements/south-spacing-ceiling-plan.json) · [Installed score](measurements/south-spacing-ceiling-score.json)

| Released nomination and later gates | Held lanes |
|---|---:|
| No same-lane straddlers | 714 |
| Lacked unique assigned straddling Graph measurements | 447 |
| Reached the original spacing rejection | 39 |
| Passed the diagnostic spacing step and unchanged alias, slope and phase checks | 39 |
| Candidate-positive / candidate-empty among the 39 | 39 / 0 |
| Passed the unchanged one-bin signed innovation check and moved | 39 |
| Installed-positive / installed-empty among the 39 | 39 / 0 |

Each eligible bracket had exactly **2.000 s before and 2.000 s after** the target, for a **4.000 s** donor interval. All 39 failed both original spacing limits. Both radio rows of each held visit were already absent from the released Graph, which reproduced **44 assigned observations, five tracks and zero curved tracks**. The diagnostic preserved the same adjacent-piece donors, zero alias lift in these brackets, 8 kHz/s slope cap, finite non-antipodal arrival arc and unchanged half-shrink on the measured winner. It kept each winner's measured arrival. The median CFO movement was 4.05 Hz and the maximum was 20.89 Hz. [Original South transfer](held-short-cfo-shrink-south.md)

| Scored set | Strict ±250 Hz and two samples | Loose ±2,250 Hz and six samples | CFO MAE before → after | CFO RMS before → after | Absolute CFO p95 before → after |
|---|---:|---:|---:|---:|---:|
| 39 edits | 39 → 39 | 39 → 39 | 16.14 → 13.57 Hz | 18.64 → 17.51 Hz | 31.70 → 39.69 Hz |
| All 228 paired held positives | 228 → 228 | 228 → 228 | 14.02 → 13.58 Hz | 16.18 → 15.96 Hz | 27.98 → 27.98 Hz |

Among edited winners, 26 moved closer and 13 farther from the installed CFO. The largest absolute error increased from 36.26 to 44.71 Hz on that subset. The other 189 positive held lanes stayed unchanged, and the remaining 972 held lanes were empty in both native packets.

The exact candidate and installed packets deduplicate the two archival South offers to a single synthetic receiver comparison. The unfiltered per-lane prehistory remains unavailable. The original history selector may have influenced donor availability before the odd mask. This is a ceiling on saved coverage with the frozen Graph, with no operational spacing recommendation or geographic evidence. One CPU3 metadata Graph reproduced the historical input, and scoring opened only saved packet and receipt files.

The protocol froze at `c481553fb`. The prediction seal was committed at `b4fa162c7` before opening the installed reference. Eight focused tests passed. Rerun the candidate-only phase with `python -m reports.ALGO08.v3.south_spacing_ceiling`, then score the sealed plan with `--score PLAN SHA256`. The archived candidate-only SHA-256 is `ae2867e1b5bd161d6778c69177951aefe00c4416363687a24b43647c64bced76`.
