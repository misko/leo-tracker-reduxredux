# Dense saved timing with forward selection and protected repair

On the sealed DS30-0008 short detector packet, forward selection and protected repair took **21.781 CPU seconds** through numerical evidence. The archived unfiltered solver took **26.105 CPU seconds** on the same input. The new result is **5.781 s** above the 16 s target. Both calibration arms failed the 250 m position screen against installed ALGO08v3. The run was a saved-input workload calibration. [Scored receipt](measurements/dense-protected-cost.json) · [Unfiltered same-input control](regional-dense-pair.md)

## Work charged to the solve

The measured solver took **21.862 s elapsed**. The entire worker took **26.299 CPU s / 27.480 s elapsed**, including the verified handoff, figure generation, eight PNG writes and readback, and receipt. The run used the same frozen worker as the DS30-0057 protected test, with the installed track graph, the native geographic and regional track libraries, exact cold-row and grid-phase reuse, and the same offered square and causal TLE archive. It used one Gauss lock on CPU 2 at nice 15 and best-effort I/O priority 7, with one numerical thread and fresh tmpfs outputs. Raw decoding and receiver work are outside the measured clocks. [Protected worker](local_future_repair_trial.py) · [DS30-0057 transfer](local-future-transfer.md)

| Disjoint solve stages | CPU s |
|---|---:|
| Forward selection and future-roster preparation | 0.318 |
| Early geographic check | 3.319 |
| Candidate discovery, gates, salvage, predictive nomination and ordinary fit | 9.482 |
| Signed qualification and fit | 0.579 |
| Protected local repair | 0.704 |
| Standard numerical evidence | 4.464 |
| Ordinary and protected exterior check dispatch, together | 0.000038 |
| Other solve work, including common preparation | 2.915 |
| Full installed fallback | 0 |
| **Total numerical solve** | **21.781** |

Forward selection retained 5,940 of 7,336 selected probe lanes. Cold discovery and the finalist race took 4.610 s inside the 9.482 s candidate stage. Rank 1 won the race. The first ordinary paired fit failed its gates. The existing single retry removed one curved and one predictive track and passed. The warm signed fit then passed. All 25 regional projections ran with native scoring, and the grid used 356 prepared phase calls. The protected stage examined 780 future-supported opportunities across 842 lane-time hypotheses, produced 350 pointwise matches and counted 16 ambiguous cases. It accepted 315 additions. Nomination and the fixed-owner refit took 0.143 and 0.530 CPU s, respectively, inside the 0.704 s total. The second exterior check determined that a reprobe was unnecessary. [Branch and clock receipts](measurements/dense-protected-cost.json)

## Numerical outputs

The complete publication contains **4,071 owned observations per arm**, a 179-point complete grid, the optimizer path, and eight independently read and decoded PNGs. The original signed detector digest ending `0a85` is unchanged and binds the new terminal. Both archived terminal digests were verified. Compared with unfiltered, both arms lost 584 observation IDs, gained 288, and changed the satellite or role on 608 shared IDs. These cross-route differences include forward selection and the original ordinary retry. The protected repair separately checks preservation of the forward fit within its callback. All eight figure bytes and pixels differ from both archived controls. [Scientific outputs and image hashes](measurements/dense-protected-cost.json)

| Build | Fixed-zero error | Fitted `c` error | Fixed-zero RF RMS | Fitted `c` RF RMS |
|---|---:|---:|---:|---:|
| Named installed ALGO08v3 | 1.639 km | 1.512 km | 129.703 Hz | 129.663 Hz |
| Unfiltered short control | 0.919 km | 0.857 km | 140.961 Hz | 140.950 Hz |
| Forward selection and protected repair | 2.298 km | 2.238 km | 136.776 Hz | 136.733 Hz |

The protected candidate worsened horizontal error by **659 / 726 m** versus installed and by **1,379 / 1,381 m** versus unfiltered, for fixed-zero and fitted `c` respectively. It reduced RF RMS by 4.186 / 4.217 Hz versus unfiltered. Within the protected run, fitting `c` reduced RMS by 0.042 Hz and horizontal error by 60 m. The two arms share observations, candidates, other priors and search budgets. The scores use the existing site authority. [Calibration results](measurements/dense-protected-cost.json) · [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

## First-four and first-sixteen timing models

The model substitutes the measured dense solver CPU for the old 26.105 s clock and keeps the previously enrolled recordings, original acquisition bytes, effective reader rates, unchanged failure charge, and publication allowances fixed. Each entry is the modeled median paired elapsed ratio and summed elapsed ratio, in that order. Both must be at most **0.500**. [Frozen timing inputs](measurements/regional-dense-budget.json) · [Updated model](measurements/dense-protected-cost.json)

| Roster | Reader rate | Previous unfiltered | Protected measurement | If dense solve reached 16 s |
|---|---:|---:|---:|---:|
| First 4 | Whole file, 135.35 MB/s | 0.833 / 0.808 | **0.802 / 0.783** | 0.760 / 0.749 |
| First 4 | Fast prefix, 231.52 MB/s | 0.587 / 0.555 | **0.556 / 0.530** | 0.514 / 0.497 |
| First 16 | Whole file, 135.35 MB/s | 0.788 / 0.771 | **0.751 / 0.750** | 0.700 / 0.722 |
| First 16 | Fast prefix, 231.52 MB/s | 0.548 / 0.549 | **0.522 / 0.528** | 0.486 / 0.50021 |

At the measured 21.781 s solve, meeting both modeled gates requires sustained effective rates of **276.10 MB/s** for the first four and **254.66 MB/s** for the first sixteen. All four scenarios miss at the measured solver and stipulated rates. These projections inherit the old acquisition and output costs. The completed saved publication supplies cost evidence, while the position regression independently rules out this protected configuration on the dense control. [Original projection method](regional-dense-pair.md)

Use `dense_protected_cost.py run NEW_TMPFS_ROOT GEOGRAPHIC_LIBRARY REGIONAL_LIBRARY` with the release interpreter and installed payload on the shared Gauss slot. Then run `dense_protected_cost.py score OUTPUT_ROOT NEW_JSON` with the checkout ahead of the payload. The output directory `/dev/shm/leo-v3-protected-dense.BqBRuP/published` retains this run's eight PNGs, both evidence sidecars, process clocks and full route receipt. Thirty-seven focused tests passed. [Runner and pins](dense_protected_cost.py) · [Component tests](../../../tests/pipeline_eval/test_dense_protected_cost.py)
