# Whole-raw comparison on DS30-0306

Installed ALGO08v3 finished in **4.482 s elapsed**. The current candidate took **5.349 s**, a **0.867 s increase (0.838× speedup)**. Both published a documented `no_active_curvature` withhold. Installed v3 ran first in this pair, reversing the order of the prior DS30-0016 comparison. [Frozen protocol](raw-band-pair-protocol.md) · [Measured receipt](measurements/raw-band-pair.json.gz) · [Earlier 808-visit result](raw-0016-best.md)

## Matched workload and decisions

DS30-0306 was the only one of 455 cohort members with 384–511 issued visits. Both runs consumed its full original signed capture from `fast8-auto-20261118-085700-a337300d-1-lower`, which the cohort marks incomplete. Each admitted 398 of 405 issued visits and recorded seven invalid captures. The 796 stereo receiver opportunities matched by digest. Installed v3 emitted 435 signed factors and the candidate emitted 529. The candidate used 110 full-aperture lane calls and 686 short-primary calls.

Each worker used the original 25 km offer, original screen center, and same signed archive of 46 snapshots at the original causal cutoff. The score independently checked the original authority, both native packets and standard terminal receipts. Both `c = 0` and fitted `c` arms have no position or RF RMS in either terminal. Neither worker published owners, a position path, a grid, or figures. The DS30 reference is the sealed operator site authority. An archived decision was visible after the eligibility rule had been assigned, so this is a newly measured pair on a known recording. [Cohort](../../2026_11_21_ds30_full/cohort.json) · [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

## Charged costs

| Boundary | Installed v3 | Candidate |
|---|---:|---:|
| Process start to sealed detections file (elapsed s) | 4.149 | 2.960 |
| Detections file to terminal file (elapsed s) | 0.134 | 2.182 |
| Terminal file to process exit (elapsed s) | 0.199 | 0.208 |
| **Full process elapsed (s)** | **4.482** | **5.349** |
| **Full process CPU (s)** | **4.478** | **5.348** |

The candidate reached the detections file 1.189 s sooner and spent 2.048 s more between detections and terminal. Its conservative time-support check was inconclusive, and the exact Graph ran once over 4,834 ordered edges and built 22 tracks. The stock-policy fallback published the withhold after no active curvature was found. The measured candidate solve used 2.176 CPU seconds. Its authenticated raw acquisition took 1.949 CPU seconds, including 0.384 and 0.763 native CPU seconds on the full and short lane calls, respectively. All six scheduled compressed-member lookaheads served 413.449 MB, for 0.066 worker CPU seconds. These instrumented scopes are nested within the charged process. The named launcher supplies whole-process and file clocks for this comparison.

The passive cache check found 0 of 119,934 payload pages resident. A single read-only conditioning pass over seven signed members read **491,238,921 bytes** in **3.159 s elapsed / 0.089 CPU s** with **959,472 input blocks**. The observed rate was 155.5 MB/s during that pass. All payload pages remained resident at each timed checkpoint. The named child recorded 2,176 process input blocks and the candidate zero. Neither recorded a major fault. The checkpoints measure waveform pages, while the process block counter covers all files. Checked catalogue, library and font staging took 0.252 s separately from both children. The first setup attempt stopped during staging due to a driver variable collision, before waveform conditioning or either measured launch. The corrected attempt performed the only conditioning pass and the only measured run of each child.

The launcher and scoring adapter reuse the earlier DS30-0016 composition and preserve its scientific source and DSO identities. Eighteen scoped component tests passed. The generalized scorer also revalidated the two already sealed DS30-0016 fixes, with eight decoded PNGs and a complete 179-point grid per worker. No raw input was reopened by either scoring step. The candidate was 1.031× faster on that 808-visit fix pair and 0.838× on this 405-visit withhold pair. Two recording pairs describe these cases and their branches. [Bench adapter](raw_band_pair.py) · [Score adapter](raw_band_pair_score.py) · [Component tests](../../../tests/pipeline_eval/test_raw_band_pair.py)

The measured launch freeze is `d6aa7bbc1`. Its actual children and seal are under `/dev/shm/leo-v3-raw-band-pair-0306-result02`. The retained receipt includes both child clocks and commands, timing boundaries, conditioning census, source and library identities, both standard decisions, and the scientific and figure checks.
