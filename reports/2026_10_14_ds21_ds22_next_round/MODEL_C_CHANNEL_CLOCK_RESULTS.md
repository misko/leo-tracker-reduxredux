# C029 channel-offset screen and matched native receiver-clock test

Neither constant channel corrections nor the tested smooth receiver-clock model
fixes C029's geographic selection. The latter improves the nearby accepted
candidate from 3.691 km to **2.169 km**, but selects the distant **83.881 km**
candidate. The original selected result is 83.390 km. The new model is not promoted.

## Constant-offset diagnostic

All five sealed ambiguity endpoints were screened on the fixed grid −1000 to
+1000 Hz in 50 Hz steps. Geography, satellite timing and existing calibration
remain fixed. Each channel and receiver/channel group is scored independently;
zero is included, every group is retained, and no offset prior is introduced.
The 205 full-window likelihood calculations cover all these groups by additive
singleton decomposition. This is a finite nuisance grid search, not a new
position estimate or proof of a continuous global optimum.

| Endpoint | Sum of eight channel NLL gains | Sum of receiver/channel NLL gains |
|---|---:|---:|
| Original incumbent | 0.000 | 18.446 |
| Ordinal 1 unshifted | 11.587 | 18.369 |
| Ordinal 1 shifted | 0.383 | 28.223 |
| Ordinal 10 unshifted | 0.000 | 29.909 |
| Ordinal 10 shifted | 5.614 | 183.429 |

All grid minima are interior. For the shifted nearby candidate, CH2's shared
offset minimum is zero. Its RX0/CH2 minimum is +50 Hz (gain 2.360 NLL), and
RX1/CH2 is −200 Hz (gain 20.458 NLL). Even independently optimizing all receiver/
channel offsets narrows the nearby-versus-incumbent difference by only 9.778
NLL units; this does not explain the original 165.851 objective gap. The grid
does not support adding simple constant channel offsets as the solution.

Five original objective evaluations and five explicit orbit predictions preceded
the profiles. Zero-offset scores reproduce source NLLs within 1e-7. Runtime was
18.184 seconds, with no optimizer calls or reference/held access.

## Smooth receiver-clock experiment

The next model adds the already tested NativeReceiverClock implementation to
the original plain native C objective. It uses original training nodes, B's
zero-affine receiver spline parameterization and precision, and original group
frame/prior. Baseline receiver lifts, native timestamps, satellite bank, timing
basis and all existing priors remain intact. The missing smooth correction is
distinct from a channel-constant offset. Negative DS22 trials do not establish
its effect on this C029 case.

The two initializers are the sealed original incumbent and the lowest-objective
accepted shifted refinement, selected solely by training score. Each model gets
both endpoints in their own original 25 km disks, with identical 20-second /
600-iteration allowances. All four fits were sealed before reference access.
Original accepted incumbent eligibility is preserved in the original arm.
The expanded arm selects only its accepted expanded fits.

Actual zero-clock qualification uses four objective calls. Both states reproduce
original objective, NLL, physical/group gradients, satellite responsibilities and
clutter probabilities exactly, with zero initial-state adjustment and feasible
original domains. All four new fits pass full physical/nuisance acceptance:

| Model | Initializer | Objective | NLL | KKT | Fit seconds | Error km |
|---|---|---:|---:|---:|---:|---:|
| Original | Incumbent | 33034.867925 | 32763.644261 | 0.000448 | 0.610 | 83.390154 |
| Original | Shifted | 33200.718561 | 32973.971821 | 0.000396 | 0.983 | 3.691118 |
| Receiver clock | Incumbent | 32922.125174 | 32623.256353 | 0.0000982 | 9.309 | 83.880558 |
| Receiver clock | Shifted | 33017.900937 | 32770.511313 | 0.000179 | 9.598 | 2.169245 |

The clock model narrows the within-model objective gap from 165.851 to 95.776,
but still prefers the distant solution. Improved frequency likelihood and an
improved unselected candidate are not improved selected localization. Total
qualification/preparation/fitting/sealing elapsed was 34.233 seconds. Fit
evaluation counts were 18, 29, 261 and 263; there were no retries or relaxed gates.

## Reproducibility

- Offset source `a02ea0a1a`; two actual-source/accounting/grid tests and Ruff pass.
- Offset output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-channel-offset-029-v1`.
- Offset result SHA256 `e21c3190f11b3c4c2d56886b635c6ef62ecef84fbcead29a7d0fb3c63f2949d4`.
- Clock source `1ff2d00f3`; actual zero nesting/clock finite-difference and matched
  four-call/original-fallback/no-retry tests pass, as does Ruff.
- Postseal evaluator `0d2930967`; premature-reference guard test and Ruff pass.
- Clock output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-receiver-clock-029-v1`.
- Clock terminal SHA256 `9fa4ec588c43c5af56e3553fb629b249c34dc4a0a11feb0ecc9f2bec937ee9bd`.
- Clock seal SHA256 `7eb362393440d43edc929523f4c9498625e6ca22399dd6bb31ea87674469153c`.

The added fits are separate from the original union/ambiguity budgets and baseline
histogram013. This is a repeatedly inspected development case with fitted c;
neither the sub-km target nor the full-dataset median target is achieved.
