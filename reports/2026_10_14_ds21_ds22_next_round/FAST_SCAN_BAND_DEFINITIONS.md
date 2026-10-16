# Fast-scan band definitions and production readiness

These terms describe channel groups in the audited eight-channel scan plan.
They do not identify different satellites, receivers, or independently verified
hardware switching states.

| Name | Channel membership | Recorded RF-label envelope | Saved LO reference |
|---|---|---|---|
| Lower band | CH1, CH2, CH3, CH4 | 10.7096875–11.6903125 GHz | 9.750 GHz |
| Upper band | CH5, CH6, CH7, CH8 | 11.7096875–12.6903125 GHz | 10.600 GHz |
| Both bands | CH1–8 | Union of the two groups | Per-channel reference above |

The envelopes span the lower-edge and upper-edge scan plans; they do not mean
that a recording samples every frequency continuously. Channel membership is
the definition of a band. Use each observation's recorded RF and scan-plan
metadata for calculations, rather than assigning a band by an approximate RF
threshold. See the [exact mapping audit](NATIVE_RF_FOUR_CASE_AUTHORITY_RESULTS.md).

## Physical prediction and calibration

For an observation with RF frequency f in Hz and radial recession velocity v
in km/s, orbital Doppler is −f × v / 299792.458 Hz. This scaling already exists
in the predictor. A higher RF therefore produces a larger Doppler magnitude
for the same radial velocity; do not apply an additional band multiplier.

The learned coefficient c is an additive receiver calibration term,
c × (f − f_center) / 1e9, with c in Hz/GHz. It is distinct from the speed of
light and from orbital Doppler. When moving a fit between half-band and full
frames, transport the complete calibration function, including its intercept,
so that changing f_center does not change its physical prediction.

Learned receiver-band shifts describe fitted relative frequency corrections.
They are not measurements of the external LNB's true LO. The audited records
label their RF mapping as a hypothesis and their calibration as uncalibrated.
The software IF-to-RF arithmetic is consistent; external hardware authority
remains unresolved.

## Current research model and evaluation

The latest fixed A-derived cohort policy fits both shared satellite weights
and shared weights with a band contrast. It uses two full-derived initializers
and preserves each source's frozen learned receiver-band shifts. Its half-band
evaluations are conditional views of the full-derived bank and calibration;
they are not independent half-only training pipelines.

The [complete 78-case report](MODEL_A_CAPPED_COHORT_RESULTS.md) and its ECDF
retain missing estimates in the denominator. The band-contrast CH1–8 result
has 74/78 estimates, a 1.738 km available-case median configured-reference
distance, and 7/78 cases within 0.5 km. Errors above 200 km remain. Full beats
both conditional halves in 33/74 complete triplets. These development results
do not establish a production accuracy improvement or meet the target.

## Release status

This publication formalizes terminology and publishes evaluation evidence.
It does not change persisted contracts, deployed predictors, or the live
scanner's model selection. A research score improvement alone is insufficient
to select a production replacement.

A model rollout needs an identified version integrated into the production
analysis port, component tests, reproducible group-randomized validation with
matched channel views and explicit failures, and qualification of the exact
release through the repository deployment workflow. Preserve the historical
curves and report the new version separately. No new RF collection is needed
to perform the existing-corpus qualification work.
