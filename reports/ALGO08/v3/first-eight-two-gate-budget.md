# What would it take to halve runtime on the first DS30 recordings?

Seven of the first eight assigned recordings yielded paired measurements. ALGO08v3 used **553.161 seconds** and the candidate used **343.834 seconds** through their measured exits. The candidate would need to save another **67.253 seconds** across those seven to halve total elapsed time. The observed summed and median paired speedups were **1.609× and 1.497×**. On CPU time they were **1.541× and 1.497×**. The recording cohort was fixed before scoring. [Field protocol](full-successor-field-protocol.md) · [Selected attempts and measured stages](measurements/first-eight-two-gate-budget.json)

| Recording | ALGO08v3 wall (s) | Candidate wall (s) | ALGO08v3 fitted error (km) | Candidate fitted error (km) |
|---|---:|---:|---:|---:|
| DS30-0107 | 2.176 | 0.619 | Withheld | Withheld |
| DS30-0049 | 18.679 | 13.600 | 1.420 | 4.040 |
| DS30-0178 | 94.459 | 56.951 | 0.387 | 0.605 |
| DS30-0019 | 107.018 | 71.490 | 0.842 | 0.375 |
| DS30-0274 | 133.811 | 65.543 | 0.206 | 0.934 |
| DS30-0330 | 107.001 | 74.487 | 0.916 | 1.017 |
| DS30-0397 | 90.017 | 61.143 | Solver failure | 0.878 |
| DS30-0452 | — | — | Awaiting verified input | Awaiting verified input |

The installed solver on DS30-0397 stopped when an orbit-phase query exceeded its interpolator's domain. Its clock ends at failure. The candidate clock includes its successful publication and verification. On the six recordings where both reached publication, elapsed speedups were **1.638× summed and 1.574× at the median paired ratio**. DS30-0452's catalogued directory had become a symbolic link. The original input check stopped before either worker started, so this recording contributes no time or geographic result to this snapshot. Among the seven measured pairs, ALGO08v3 published five fixes and the candidate published six. The candidate improved fitted error on one of the five shared fixes.

## Savings needed in each stage

The table gives the fraction of current candidate wall time that would have to disappear **within the named stage**, uniformly across cases, to pass both 2× timing gates. Each row holds every other stage fixed. The first gate uses summed time. The second recomputes the median of per-recording candidate-to-installed ratios after each hypothetical change, so the recording at the median may change. [Calculator and input checks](full_successor_stage_budget.py)

| Candidate stage changed | All seven measured pairs | Six pairs reaching publication on both builds |
|---|---:|---:|
| Native detector callbacks alone | 77.6% | 75.5% |
| Acquisition outside detector callbacks alone | 52.1% | 47.7% |
| All authenticated acquisition | 33.8% | 29.2% |
| Position decision and publication alone | 66.8% | 66.5% |
| All acquisition, decision and publication at the same rate | 25.8% | 21.9% |
| Decision and publication, **if acquisition already takes 25% less time** | 28.3% | 12.7% |

The candidate spent **226.204 s** in acquisition, including **97.154 s** in detector callbacks. Position decision and publication took **106.889 s**. The remaining **10.741 s** includes launch, routing, verification and other overhead. Elapsed acquisition outside the callbacks includes exposed storage waits. CPU savings in a worker thread can overlap other work and need a timed end-to-end comparison. Two pairs had a storage deferral between builds. All location and runtime claims here apply only to the enrolled Gauss recordings. [Four-pair receiver support comparison](ds30-owner-support-four.md)
