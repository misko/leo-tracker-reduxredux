# Frequency uncertainty and weak-signal ablation

Reuse all 168 archived pilot frames from the first-record DS7/DS8/DS9 split
experiment, without new IQ reads, candidate substitutions or geographic inputs.
The earlier negative point-estimator results are already exposed. This is a
new, explicitly exploratory model, not a fresh blinded confirmation panel.

Use the same alternating even-Qin training/held symbols. Each tone has independent
complex Gaussian noise, with its variance fixed to its training mean squared
magnitude. This scale includes signal power; it is a deliberately simple,
training-only empirical-Bayes choice, not a calibrated noise estimate. The signal
is a common residual frequency and independent complex Gaussian tone gains with
prior variance equal to the tone noise variance (kappa=1). Integrate the gains
analytically. Use a uniform discrete frequency prior on -2000:10:+2000 Hz.
The null is independent zero-mean complex Gaussian noise at the same scales.
For signal/null models, prior odds are 1:1. Freeze all settings; no tuning on
held symbols, dataset scores, or position errors.

Five arms: fixed acquisition residual zero, training-only ordinary profile point,
frequency mixture (all signal), fixed zero plus null, frequency mixture plus null.
This separates frequency uncertainty from adding the noise-only hypothesis.
All arms use the same training scales and gain prior. Point-estimate selection
is empirical and does not integrate its selection uncertainty. Evaluate proper
conditional held log densities with training posterior gains and weights; held
symbols do not refit gain, frequency, scale, model probability or any parameter.
Report per-window paired gains relative to fixed-zero signal, and relative to
noise-only. Aggregate equally over windows, separately for each dataset. Do not
report the old profiled-coherence and new predictive-density scores as the same
quantity. Retain all frames including weak/boundary cases.

Apply the same seeded held-symbol QPSK controls at frozen training posteriors.
Report real and scrambled predictive densities without using the control to tune
weights. Retain conditional frequency weights, signal probabilities and noise
scales for audit. These are model-conditional weights, not calibrated physical
signal-presence probabilities or emitter identities.

For ±250 Hz phase ramps on the entire archived matrix, check two distinct cases:
(a) translate the frequency prior support by the same known shift; posterior
weights and held densities should be unchanged within 1e-8. This is an exact
change-of-coordinates check, not a measurement gain. (b) keep the acquisition
search interval fixed and report posterior-mean shift error without hiding
boundary or weak cases. Separately identify training-only reliable pairs where
both signal probabilities exceed .99 and original conditional frequency mass
that stays inside the shifted fixed interval is at least .99. These diagnostics
do not make the posterior mean a promoted measurement.

Advance this model toward a larger waveform/geographic ablation only if it
improves real held density relative to fixed-zero signal on every dataset,
improves relative to noise-only on every dataset, and keeps all reliable-pair
mean shift errors within 5 Hz. Also report mixture-versus-point and
null-versus-signal increments, even if the overall gate passes. These necessary
checks cannot establish frequency truth, receiver tilt benefit or sub-km accuracy.

Each dataset job has a 60-second/2-GiB cap, one numerical thread, nice19; jobs
run sequentially, no retries or replacements. Archive all terminal receipts,
training posteriors, results and source/input hashes. Verify Gaussian algebra
against dense covariance calculations and test synthetic recovery, noise-null
behavior, posterior normalization and translated-domain invariance.
