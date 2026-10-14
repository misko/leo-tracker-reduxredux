# DS21-039: saved-state timing/calibration interaction and assignment attribution

Status: implementation qualified before dataset execution. The component and runner pass **32 tests** and Ruff checks. The target remains improved localization across DS21, with less than 0.5 km per eligible recording. This diagnostic does not itself estimate a new position.

The completed band-calibration control improved training and held likelihood but worsened position error from 4.072515 to 4.186817 km. Separately, the original model's fixed-geography nuisance profiles retained a pronounced minus/plus asymmetry at the refined endpoint. The next question is which actual nuisance adjustments and observations produce that asymmetry, and whether satellite/native-frequency assignments, visibility or orbit interpolation changes accompany it. No timing prior is tuned using position error.

## Exact saved states and calls

Bind the completed original-model [fixed-geography profiles](FIXED_GEOGRAPHY_TIMING_PROFILE_RESULTS.md), their source archive, four retained stationary fits, exact first-step displacement starts, and original curvature/displacement/refinement/input ancestors. Historical receipts retain their original scope. Verify original observation preparation, candidate identity/order, native timestamps, physical frames and six source proposals. The all-band 43-satellite model, observations, singleton likelihood, neutral waveform evidence and fitted common `c` remain unchanged.

Make exactly two original endpoint replay calls, then four original objective/gradient calls for each of the four saved fixed-position fits: **18 calls, zero optimizer calls**. The two endpoints are original-all and refinement-free. The four fixed positions are their already prescribed step-0 minus/plus 1 km displacements; no new direction or reference-derived position is introduced.

At each fixed displaced position, evaluate the complete 2×2 nuisance factorial:

| Cell | Receiver calibration, fitted c and group offsets | Common/relative satellite timing |
| --- | --- | --- |
| Geography | Original endpoint values | Original endpoint values |
| Calibration | Saved fixed-position fitted values | Original endpoint values |
| Timing | Original endpoint values | Saved fixed-position fitted values |
| Full | Saved fixed-position fitted values | Saved fixed-position fitted values |

Every cell uses the same displaced geography. Source arrays are copied; original objective, orbit prediction, gradients, likelihood and priors remain unchanged. Validate all mixed states against the original physical/coefficient constraints and exact native interpolation support before evaluating them. Both endpoint replays and all four full cells must reproduce saved objective/NLL values within 1e-7. Preserve the common-timing, relative-timing and group-offset prior ledger separately from likelihood effects. These fixed mixed states are diagnostics, not stationary contenders.

## Attribution and interpretation

For every cell, retain per-window NLL, satellite/clutter posteriors and native-frequency responsibilities on identical ordered support. Record native visibility, sampling-ambiguity integers and the original orbit-kernel interpolation cells. Evaluate Doppler and corrections at native receive times. Do not drop windows whose support changes or renormalize visibility priors.

Report the finite likelihood interaction `full - calibration - timing + geography`, its per-window contributions and closure to the scalar total. Report prior and complete-objective interaction separately. Compare each nuisance cell to the geography-only cell, and the full cell to its original endpoint. Include posterior total variation and maximum-posterior label changes, keeping satellite/clutter allocations distinct from native-frequency alternatives. Attribute totals by original counter-defined training block, receiver and band; retain held-block gaps. Persist every window contribution rather than selecting only large examples.

Split interaction totals between changed and unchanged visibility support, and record interpolation-cell/sampling-integer changes without treating those transitions alone as numerical faults. Interpolation cell changes can be part of valid continuous interpolation. Posterior switches are model allocations, not measured transmitter identities. Block counts and posterior masses do not establish independent samples or statistical significance.

This analysis can identify concentration, interaction and discontinuity candidates for a subsequent controlled intervention. It cannot establish true satellite timing errors, globally optimized nuisance profiles, accurate geography, a hardware law or a justified replacement prior. No held preparation, reference read, new RF collection or QNAP mutation is included.

## Qualification, receipts and budget

Required tests cover exact unchanged native evaluation capture without mutating the source model, manual factorial state assembly, per-window/scalar interaction and prior closure, native timestamps, missing visibility, alias transitions, invalid/nonuniform orbit-bank nodes and malformed/alignment inputs. Runner tests must cover parent/source tampering, exact saved-state identity, bounded call inventory, failure retention and cached reads without preparation or numerical calls.

The qualified array component is committed as `f99e0996a`. Its copied-instance capture avoids the original calibration wrapper's recursive copy-protocol lookup without changing any original numerical field or method. Tests distinguish satellite/clutter, native-candidate/clutter and joint candidate/satellite allocation changes. The runner verifies the historical 340-source profile authority directly, binds cached state plans to the original profiles, and checks exact metadata/captured window order before grouped attribution. A failed saved-scalar replay retains its raw result and native archive while remaining a failed attempt.

Freeze the qualified sources and exact parent bindings before execution. Record an outer launch before validation/preparation, and a launch/result/termination for each prescribed call. Seal the endpoint/cell arrays, attribution results and complete outcome inventory. Failed or orphan attempts cannot be retried. A cached result must revalidate source, parent and result seals before returning. The complete process, including preparation, 18 evaluations, compression/writeout and final verification, has **90 seconds internally, TERM at 105 seconds and KILL at 110 seconds**, with one BLAS thread and no other heavy dataset process running.
