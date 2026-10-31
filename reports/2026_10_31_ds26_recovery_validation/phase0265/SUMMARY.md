# DS26-0265: phase convergence repaired; full inclusion rejected

Expanding the **numerical phase reference** from ±15 s to ±30 s fixes the diagnosed clipping of the unrelated calibration family 52311. This changes neither its physical prior nor the target’s phase support. The existing causal orbit bank supports every reference update; no orbit bank extension, extrapolation, new TLE, or RF collection was used.

The comparison replays the same three saved random grouped partitions in both `c = 0` and fitted-`c` arms: six fold/arm fits per reference limit. Observations, candidates, aliases, priors, starts, and search budgets remain matched. The ±15 s scores reproduce the frozen results within `1e-5`; training and held masks match between variants. Each fit uses five phase rounds and at most 48 position iterations per round.

| Result | ±15 s reference | ±30 s reference |
|---|---:|---:|
| Maximum final phase movement across six annotation fits | 0.198 s | 0.00000723 s |
| Annotation fits passing the 0.01 s phase gate | 0 / 6 | 6 / 6 |
| Shared winning target identity | 66102 | 66102 |
| Held target RMS across folds and c arms | 86–178 Hz | 86–178 Hz |
| Minimum held competitor score margin | 686.74 | 686.74 |

The broader reference restores conditional identity support without materially changing the frequency scores. It does **not** establish full inclusion. At ±30 s, the matched control passes the RF, phase, exact-orbit, and ownership checks. Adding the target produces RMS **110.99 Hz (`c = 0`) / 110.19 Hz (fitted `c`)**, but fails the unchanged quadratic and step residual-structure gates in both arms: exact-target quadratic BIC gains are **16.50 / 14.61** against a maximum of **10**, and maximum step z values are **5.06 / 4.87** against a maximum of **4**. The final phase movements are below `0.000011 s`, and maximum exact-orbit prediction differences are below `0.000074 Hz`. Existing memberships and owners are preserved. The trial proposes 120 additional points; **none are accepted**.

Known-site coordinates enter only after inference is sealed. With the ±30 s reference, position errors are **134 / 58 m** for the control and **170 / 115 m** for the proposed addition (`c = 0` / fitted `c`). The addition worsens position accuracy in both arms. Frequency fit and position accuracy are separate outcomes; neither the phase fix nor conditional identity support establishes a localization improvement.

![Matched phase, residual-gate and reporting-only position comparisons](figures/DS26-0265-phase-reference.png)

Figure A shows unclipped phase movement, B the target’s profiled residual, C the exact-target RMS and structure statistics divided by their unchanged thresholds, and D position error evaluated after inference. In C, values above one fail. The ±450 Hz lines in B show the RMS scale, not a pointwise acceptance rule.

Evidence: [annotation comparisons](matched-run01/annotation_summary.json), [full reporting summary](shared-run01/reporting_summary.json), [30 s control (gzip JSON)](shared-run01/reference30/inclusion/control.json.gz), [30 s addition (gzip JSON)](shared-run01/reference30/inclusion/target_0.json.gz), [exact-orbit and owner replay (gzip JSON)](shared-run01/reference30/inclusion/exact_owner_replay.json.gz), and [inference seal](shared-run01/inference_seal.json). Two focused tests pass. Initial route and metadata-write failures remain recorded in [raw evidence](raw-evidence.tar.gz); completed fits were reused rather than silently discarded. No production or frozen scientific artifact changed.
