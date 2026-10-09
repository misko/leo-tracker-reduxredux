# Decision after the full148 paired-receiver audit

**Hold the proposed position-refit experiment while investigating the user's new
failure. The surviving satellite contrasts are small after accounting for the
existing smooth-clock span. This audit establishes no position improvement.**

All148 consumed DS16/17/18 members completed: DS16 63 (original48 plus15), DS17 51,
DS18 34 (prior24 plusother10). No exclusions, missing inputs or failures occurred.
Both existing B7 endpoint objectives reproduce exactly:296/296 reconstruction
deltas equal0. All1983 frozen closure hashes pass. This is a diagnostic of those
unchanged endpoints, not a new position fit or independent validation.

| Median per-recording mean absolute eligible satellite contrast, Hz | fitted-c | c0 |
|---|---:|---:|
| Raw paired satellite means, including common effects | 23.944 | 39.610 |
| Unadjusted zero-sum shrinkage | 8.849 | 15.979 |
| Intercept, linear time and channel projected | 5.583 | 9.498 |
| Existing B7 smooth-clock span also projected | 1.874 | 1.709 |

Both arms retain the exact same33665 pairs,30862 eligible pairs and826 eligible
recording/satellite groups. The comparison uses the same fixed30Hz contrast prior
and pair precision1/31250Hz². The latter is an uncalibrated equal-noise working
approximation, not an independence or hardware-noise claim. Residuals differ by
arm, but assignments and pair support share ordinary fitted-derived B7 geometry.

Projection removes distinguishable common clock/channel contributions before
estimating satellite contrasts. Adding the actual smooth-clock span lowers the
median identifiable contrast-rank fraction from1.0 to0.8; no-ops rise from14 to21.
Those lost modes are confounded under the frozen model, rather than evidence of
a satellite-specific hardware defect. The reduction also reflects the fixed
regularization acting on less identifiable information. It must not be interpreted
as an additive physical variance decomposition or proof that every remaining
effect is correctly modeled. Some recordings retain larger contrasts, and the
full distributions/ranks remain in [RESULTS.md](RESULTS.md) and [summary.json](summary.json).

The fitted-c dataset medians after smooth projection are2.100Hz for DS16,
1.851Hz for DS17 and1.444Hz for DS18. The evidence does not support increasing a
prior or choosing a special correction per scan to manufacture a larger effect.
Retain the prepared solver and its synthetic qualification; defer iteration92
position fits while the explicit newer user failure is investigated.

An antisymmetric receiver correction also cannot directly improve the common
spatial gradient for ideal balanced simultaneous Gaussian pairs with fixed
assignments. Any localization benefit would have to emerge through unequal
support, calibration coupling or associations, and needs a controlled same-start
position experiment. A narrower frequency residual by itself supplies no measured
position-error gain and does not establish the0.4km objective.

Production B7 is unchanged. The existing11-member reserve and the new8-member
reserve remain closed by this diagnostic. Reference coordinates/errors played no
role in grouping, solver inputs or operational selection. Future validation must
retain full membership and matched c0/fitted-c policy, disclose fitted-derived
conditional calibration, and report frequency-fit effects separately from position.

[verification.json](verification.json) records objective/hash checks and all raw
receipt digests. [receipts.tar.zst](receipts.tar.zst) contains all148 immutable raw
diagnostic receipts; streaming re-read verifies every archived SHA256 against its
original file. Both worker sessions terminated successfully without replacement.
