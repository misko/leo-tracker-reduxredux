# Matched waveform correction replication on original DS11 index16

This follows the completed scan0 experiment, in which long-pilot corrections
reduced reference error by13.810m and short-pilot corrections worsened it.
A subsequent prospective nominal-support comparison gives19.730m improvement
for long and2.160m worsening for short. This scan16 protocol is amended before
any new waveform measurement, plan freeze or position fit to use that nominal
support policy. The runner reuses the verified support-aware interpolation
and freezes each arm's per-observation nominal support offsets.
Scan16 is the other scan with a completed original source-influence diagnosis.
Within it, choose the physical NORAD with the largest exact original-IID
source-deletion EN movement among all18 qualified source folds; break ties by
lowest NORAD. This fixed training-only rule identifies NORAD67103, with a
1839.721532m deletion movement and three tracks containing124 training and81
localization-held observations. No new waveform or corrected-position result
selects the scan or source. The reference and scan are already exposed; this
is a mechanism replication, not blind-site validation.

Carry both original pilot arms into a matched IID position comparison, with
no arm selection from waveform-held scores. Require all124 waveform rows to
have completed and neither arm to have a frequency-search-bound hit before
fitting either arm. Otherwise retain the complete124-row denominator and report
this positioning replication unavailable; do not filter, replace or retry rows.

Apply each arm's direct canonical corrections to all124 exact training rows.
Preserve aliases, candidate mixtures, causal orbit states, masks,
the81 target localization-held timestamps and values and every other measurement.
For each corrected training row and each candidate, evaluate the existing
state bank at the nominal eight-frame pilot FFT center using the verified
support-aware interpolation. Preserve the original stored observations and
record these time offsets separately. Use the same t4/100-Hz likelihood, CFO
profile, altitude and timing grid as original IID, with the5ms timing-boundary
guard used in the scan0 support-aware comparison. This is nominal geometry,
not a claim to have measured amplitude-dependent estimator weights.
Retain the cached original IID control only after exact
score replay within1e-6nats and fresh gradient/finite-difference qualification.

Each arm gets four starts: original IID x and generic(-2,0,0),(0,0,0),(2,0,0)
in km,km,seconds. Freeze all eight jobs before fitting. Keep the original
L-BFGS-B settings and qualification checks,90seconds per start, one BLAS thread,
at most three concurrent workers, and every terminal result. No numerical
recovery or retries. Select the highest-training-score qualified endpoint per
arm and persist both selections before any geographic scoring. Both arms must
have a qualified endpoint; otherwise report the comparison unavailable.

Report all eight attempts and both arms. Qualified endpoints receive held
likelihood under the original measurement model and the corrected-training
model, with localization-held data unchanged. Report reference errors only
after both selections are sealed. A directional replication of the long-arm
gain requires complete measurement coverage, both qualified arms, and lower
long-arm error than original IID on this scan. This does not by itself qualify
either arm for promotion or demonstrate a general DS11 improvement. No
threshold, correction, source or arm may be retuned using these results.
