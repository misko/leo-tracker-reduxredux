# Receiver-path frequency calibration campaign

WP11 uses a separate, predeclared calibration campaign before any acceptance
capture. For each fixed Pluto+ serial and physical RX1 chain, schedule at least
three independent 60-second CH4-lower dwells with the frozen 2.5 MS/s profile.
Those raw captures are calibration-only and must never be reused as acceptance
IQ.

`FrequencyCalibrationPlanV1` freezes the radio ID and serial, RX1 physical-path
identity, hardware/topology epoch and its evidence digest, profile digest,
scheduled session IDs, robust estimator, minimum candidate/session counts,
dispersion and multimodality limits, and frequency-coverage bounds. Every
scheduled dwell is retained in `FrequencyCalibrationEvidenceV1`, including a
dwell that produced no usable candidate. A manifest digest, profile digest,
candidate-extractor digest, observation digest, capture interval, exact sample
geometry, and topology identity bind each observation.

The estimator is a median with MAD-based outlier rejection. The uncertainty is
the full observed inlier radius plus the predeclared measurement allowance; it
is deliberately conservative. Evidence is `insufficient` if candidate or
session minima fail, the retained population is too dispersed or multimodal,
the pilot, uncertainty, and a 300 kHz satellite-Doppler guard do not all fit in
the sampled band, or the frozen residual search cannot cover both uncertainty
and that guard. Digital search is not allowed to excuse pilot energy that would
be clipped at the sampled-band edge.
Insufficient evidence emits neither a calibration nor a calibration set. There
is no zero or historical-center fallback.

The result is an **empirical pilot acquisition/search center** for one hardware
epoch. Blind pilot CFO includes satellite Doppler, so it is not an estimate of
intrinsic LNB error. An accepted result produces content-addressed
`ReceiverFrequencyCalibrationV1` and `ReceiverFrequencyCalibrationSetV1`
contracts whose evidence points to the immutable campaign receipt. Validity is
half-open and starts strictly after the final calibration dwell; a topology or
path change requires a new epoch and campaign.

Hardware execution remains an operations step: complete the current soak,
capture the separately tagged calibration sessions for each radio/RX1 path,
run the frozen candidate extractor, review the immutable receipts, and only
then begin the independent and synchronized acceptance captures.
