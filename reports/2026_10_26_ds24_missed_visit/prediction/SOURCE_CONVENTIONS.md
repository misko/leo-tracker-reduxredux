# Convention check for timing/CFO coupling

The historical public scorer uses `frame_start = epoch_sample + round(frame *
frame_period)` and samples beginning at that index plus the fractional offset.
It derotates samples by `exp(-2j*pi*cfo_hz*absolute/sample_rate_hz)` and reports
tracking CFO as acquired plus residual CFO. Thus positive digital epoch selects
later recorded samples, and positive CFO denotes positive complex sample
frequency. The analytic known-pilot generator uses the same delay and frequency
conventions. These are digital scorer conventions, not a verified mapping from
RF radial velocity through every receiver/LO/IQ stage.

Verified native metadata gives `actual_if_center_hz`; the target carries
`rf_center_hz`, `lnb_lo_hz`, and explicitly `rf_mapping_authority: hypothesis`.
The recorded metadata identity `RF center - LNB LO - actual IF center = 0` does
not by itself verify physical complex sideband orientation, IQ conjugation,
oscillator/sample-clock coupling, or satellite signal identity. The diagnostic
uses the archived probe's `actual_rf_hz` as requested, with exact native Fs.

For a simple propagation-only model with increasing epoch meaning increasing
path delay tau, epoch phase is +Fs*tau and positive received Doppler is
−f_RF*tau_dot. Under that fully verified orientation, timing acceleration would
be −(Fs/f_RF)*Doppler_slope. The observed closer relation here has the PLUS sign.
Therefore the observed scale match cannot yet be labeled propagation physics.
It could motivate a separately declared empirical RF-scaled predictor, while
RF/LO/IQ/clock conventions and candidate identity remain unresolved.

No target epochs or target CFO values enter `coupling_diagnosis.py`. All 362
primary histories with at least three earlier donors remain, including
outliers. The median acceleration/(Fs/RF*CFO_slope) is 0.99465, but Pearson
correlation is only 0.295 and the positive-relation residual RMS is 1.332
samples/s². Both signs, per-channel/RX statistics and each coefficient's
conditional OLS SE are retained. Engineering floors 0.75 sample and 75 Hz
prevent a near-exact fit from pretending to have known zero uncertainty.
These SEs assume the chosen regression/association model and do not establish
independent or calibrated RF errors. Shared donors further limit any inferred
population significance. No estimator, target prediction or raw score changed.
