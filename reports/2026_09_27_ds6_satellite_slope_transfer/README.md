# Satellite-associated slope transfer: insufficient repeat coverage

The frozen opposite-subset transfer diagnostic completed, but **zero target tracks qualified for a correction**. This is a coverage result, not evidence of predictive improvement, rejection of satellite-related model error, or improved geographic accuracy.

| Subset | Eligible tracks | Distinct training-MAP satellite candidates | Candidates seen in at least two donor scans |
|---|---:|---:|---:|
| A | 387 | 219 | 1 |
| B | 316 | 193 | 1 |

Only one candidate NORAD number appears in both subsets. Neither repeated-donor candidate appears among eligible opposite-subset targets. Thus no target meets the frozen requirement of at least two independent donor scans. The zero aggregate score change in summary.json means no correction was applied, not that a nonzero correction was tested and found neutral.

Eligibility was fixed at training-MAP posterior >=0.95 and training span >=30 seconds. Exact propagated predictions at the validated A/B subset positions yield residual traces. Per-track training OLS slopes would be combined by median within each donor scan, then median across donor scans for each NORAD number. Target constant offsets would be refitted using training visits only after applying the opposite-subset correction; held-out observations and geographic reference cannot set the correction. Candidate row indices are explicitly mapped through the matching causal catalogue to NORAD numbers.

The test uses training-selected candidate identities, not independently decoded identities. Its coverage limitation may reflect both pass geometry and association ambiguity. Subset positions differ, which can also affect fitted slopes. This is a conditional fixed-position diagnostic with reused observations; no geographic search or production change occurred.

Three tests cover donor scan balancing, the two-scan requirement, synthetic slope recovery, held-out isolation, frozen inputs, eligible trace support, and exact transfer coverage. The original rule remains unchanged after observing insufficient coverage. A future useful correction must transfer across different visible satellites or use independently supported orbit/receiver calibration, rather than assume repeated-satellite training evidence exists in DS6.
