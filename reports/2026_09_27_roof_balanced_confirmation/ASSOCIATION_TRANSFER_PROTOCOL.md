# Conditional RX-to-Doppler association-transfer diagnostic

## Question and scope

Does receiver-direction evidence improve prediction of separate Doppler
observations after updating the candidate identity distribution? The negative
dual geographic result motivates this calibration-only test. It is not a new
location estimator, proof of physical satellite identity, or geographic
confirmation. Use the original six calibration recordings / 344 topology-
retained tracks / 6,378 reserve reception rows only. Do not inspect unused
confirmation outcomes or search new positions.

The frequency scale and degrees of freedom remain 130.0352477522671 Hz and
1.5307006392659719. They were estimated using all six recordings, so the test is
conditional on that frequency calibration, not fully nested generalization.
Receiver coefficients, feature schemas, shared detection sigma and ratio tau
must instead come from the accepted leave-one-recording-out artifacts that
exclude the recording being scored. No parameter is refitted or selected here.

## Observation separation

Rebuild each recording at its calibration coordinate through the existing
digest-bound public input/catalogue adapters. Preserve the original training
mask, training-only full-catalogue shortlist and CFO. Reproduce the frozen
frequency extraction where available. The training mask is interleaved:
**this test is not future-time forecasting**.

Within each track, form atomic groups using overlapping public source sample
intervals within the same source group (ignoring receiver stream), common RX
opportunity keys, and matched physical-pair keys. Include original training
observations in this grouping. A component containing training observations
cannot supply conditioning or held reserve observations; explicitly account for
such exclusions. Validate raw-window separation, rather than assume different
observation IDs imply different acquisitions.

Define the temporal midpoint from the minimum and maximum reserve support UTCs.
Use a fixed 120 ms total boundary guard: an atomic component enters early A only
when every reserve center is strictly before midpoint minus 60 ms, and late B
only when every center is strictly after midpoint plus 60 ms. Otherwise exclude
the entire component and record the reason. Never split a reciprocal pair or an
equal-time/group tie. No signal strength, residual, candidate score or geographic
error may affect grouping or eligibility.

Both halves must be nonempty; otherwise record unsupported status without
changing the split. Include sparse one-observation halves and report the complete
count distribution. No outcome-based minimum-count filter is allowed. Groups
are independent only with respect to audited raw-window reuse; temporal
correlation and cross-track dependence may remain.

## Prediction comparison

Let w be the normalized frozen training frequency candidate distribution,
F_A and F_B the summed candidate Student-t frequency log likelihoods in the two
reserve blocks using the unchanged training CFO, and R_A the candidate RX log
likelihood using only A. For the forward direction:

    q_F  = normalize(w * exp(F_A))
    q_RX = normalize(w * exp(F_A + R_A))
    NLL(q, B) = -log(sum_k q_k * exp(F_B,k)) / count(B)

Both arms use exactly the same frequency evidence. Candidate identity is shared
across all held observations and marginalized once, not redrawn per row. B must
never affect either conditioning distribution. Integrate one detection offset
across A using accepted mode-centered 64-point quadrature, verify 128-point
agreement <=0.001 per candidate, and integrate the ratio offset analytically.
Use only A's matched ratios and detection outcomes. Preserve normalizations.

Run the reciprocal B-to-A direction as well; report it separately, not as an
independent recording. Predeclared controls are reversal of the frozen
directional terms and candidate-independent reception likelihood (which must
cancel from association probabilities). Do not choose orientation or model
weights based on the result.

## Reporting and decision

Persist per-recording eligibility/guard/provenance accounting, candidate IDs and
aligned likelihood vectors, conditioning probabilities, per-track predictive
scores, all parameter/input/code hashes and numerical receipts. Refuse output
overwrite. Report every recording and both directions, with occupied-second
track-weighted and equal-track mean NLL, plus eligible/unsupported counts.
Positive baseline-minus-RX NLL is improvement; disclose regressions and compare
the reversal control. Do not treat individual rows as independent replicates.

This is a diagnostic, not an automatic promotion gate. A positive average alone
does not prove location accuracy, especially if concentrated in one recording or
matched by the reversed-direction control. A negative result argues against
further geographic runs of the unchanged RX association update. No confirmation
recordings, new RF acquisition, production changes, or writes to source recordings.
