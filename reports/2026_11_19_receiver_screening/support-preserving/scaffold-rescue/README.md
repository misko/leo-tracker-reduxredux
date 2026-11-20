# Fixed-scaffold rescue

The experiment adds stock-negative FFTW measurements to existing Graph tracks. It builds each stock Graph once and retains the original members and their exact CFO branches. It uses four complete saved-IQ detector pairs. DS26-0168 and DS29-0604 are diagnostics. DS26-0237 and DS29-0082 form a separate replication on previously studied recordings. All use the same original 25 km offer, causal TLE archive and phase-release numerical code. [Frozen protocol](PROTOCOL.md) · [Input authority](plan.json)

An attachment requires a unique existing track on the same receiver, channel, edge and RF. Its original members must bracket the proposal within 0.8 s on each side, and one original polynomial piece must predict the donor within the native 450 Hz residual threshold after the nearest configured alias lift. The solver sees the donor's original CFO as its raw observation, alongside its deterministic lifted copy in the track. The stock curvature groups, noise coefficients and per-point weights, orbit bank, and phase history stay fixed. New observations use the existing stock noise law. The position receiver can choose different orbit associations with the augmented evidence.

The first integration reached attachment on all four recordings and stopped at the likelihood's missing per-observation noise entry. The repaired adapter evaluates the already fitted stock noise law at each appended margin while retaining every stock coefficient and lookup entry. The position results below refer to the repaired run. [Integration amendment](INTEGRATION.md) · [Original four failed attempts](initial-integration/prediction-lock.json)

## Fixed groups and actual positions

The fitted receiver preserved all **425 stock groups**, **13,664 original group memberships with exact lifted CFO and time**, and **14,990 raw stock CFO observations**. Independent installed Graph preparation reproduced every attachment choice and verified each original group member and branch. Of 1,609 stock-negative donors, 73 attached, 1,493 lacked a close stock bracket and 43 were outside the CFO gate. No donor matched multiple eligible tracks. The attachment uses only the stock track fit. [Per-group member IDs and raw/lifted measurements](group-branches.jsonl.gz) · [Preservation and gate counters](group-support.csv)

All four services published both calibration arms. Entries are `c = 0` / fitted `c`. Stock and fixed rescue each met the within-10%-of-original-v5 target on **3/4 / 2/4**, and unfiltered FFTW met it on **2/4 / 2/4**. Fixed rescue improved on stock by 32 / 29 m on the hard DS29-0082 replication, with 2.457 / 2.317 km remaining error. The other three recordings were less accurate than their stock controls in both arms. On DS26-0168, preserving the scaffold recovered some of the large unconditional FFTW loss and still increased fitted-calibration error by 0.332 km against stock. [Coordinates and conditional RF metrics](scores.csv) · [Four archived original v5 options](capture-era-v5.csv)

| Recording | Cohort | Donors attached | Stock error (km) | Fixed rescue error (km) | Unfiltered FFTW error (km) | Stock → fixed rescue RF RMS (Hz) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0168 | Diagnostic | 19 / 401 | 0.805 / 0.796 | 0.868 / 1.128 | 1.724 / 1.722 | 70.86 / 70.87 → 70.94 / 70.97 |
| DS29-0604 | Diagnostic | 12 / 401 | 0.735 / 0.734 | 0.741 / 0.740 | 0.760 / 0.775 | 95.52 / 95.48 → 95.75 / 95.70 |
| DS26-0237 | Replication | 24 / 461 | 0.382 / 0.323 | 0.394 / 0.335 | 0.295 / 0.221 | 92.54 / 92.43 → 92.49 / 92.37 |
| DS29-0082 | Replication | 18 / 346 | 2.489 / 2.346 | 2.457 / 2.317 | 2.296 / 2.055 | 84.42 / 84.25 → 84.57 / 84.39 |

DS26-0237's RF residual fell slightly with the fixed scaffold as its position worsened. Across the four recordings the strict local rule retains the measured stock support and gives mixed position outcomes. The solver uses its original search and five-refresh cap in both calibration arms. Its selected associations can move when the added measurements change the likelihood. [`c = 0` chart](charts/c0/fixed-scaffold-rescue.png) · [Fitted `c` chart](charts/fitted_c/fixed-scaffold-rescue.png)

## Raw detector work, buffering and fitting

The detector work ledger comes from the two actual archived passes on each complete saved-IQ recording. It verifies the same physical visit support and reports each measured detector CPU clock separately. A modeled stock-first route invokes the full FFTW call once whenever either stock receiver is negative. It uses the exact paired visit clocks and reports serial deadline outcomes. This model excludes scheduling and position work. [Full timing ledger and scenario](time-work.csv)

| Recording | FFTW on stock misses | Stock / standalone FFTW mean measured detector CPU (ms) | Stock-first mean modeled detector CPU (ms) | Serial modeled visits within 20 ms | Median attached-observation wait to full sample frontier (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0168 | 4,990 / 6,774 | 24.80 / 18.04 | 37.67 | 6 | 183.2 |
| DS29-0604 | 5,664 / 6,756 | 23.85 / 28.09 | 47.05 | 15 | 148.7 |
| DS26-0237 | 5,544 / 6,766 | 15.31 / 32.42 | 41.34 | 1,097 | 187.1 |
| DS29-0082 | 4,408 / 4,868 | 25.88 / 31.99 | 54.54 | 0 | 195.2 |

Using both complete detector streams requires 42.84–57.86 ms summed CPU per visit across the four recorded workloads. These clocks came from separate host services. Every attachment waited for the full stock Graph at approximately the 300 s sample frontier. The wait column measures the gap from each accepted probe to that frontier, before preparation or fitting. The 0.8 s local bracket alone gives no acquisition-time shortcut. No new raw acquisition or live buffered detector execution was measured.

Actual corrected services measured 38.57–146.03 CPU s and 39.06–155.91 wall s, including native preparation and inference. Stock preparation, including Graph, sky and noise, used 13.02–20.49 CPU s. The extra attachment stage used 10–91 ms CPU. Maximum cgroup charge was 426.7 MiB under the enforced 512 MiB no-swap limit with zero OOM. All position work starts from stored factors. [Position resources](position-work.csv) · [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json)
