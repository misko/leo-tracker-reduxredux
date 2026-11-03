# GLRT detector alternatives: bounded prototype protocol

Frozen design: October 7, 2026. This is a research-only comparison over existing
recordings and seeded simulations. Production configuration, persisted contracts,
golden fixtures, and RF collection are outside this experiment.

## Question and decision

Does replacing the current normalized pilot-coherence margin improve detection
under controlled models, or produce more consistent frequency evidence on saved
IQ? The current detector remains the default unless independent evidence supports
a later qualification. A higher score or more retained candidates is not itself
an improvement.

The experiment separates three questions:

1. Mathematical correctness of the proposed statistics.
2. Conditional detection and frequency estimation when timing is already acquired.
3. Candidate ranking and frequency consistency after a common acquisition search
   on unlabeled real recordings.

Neither conditional simulation nor agreement with the current detector establishes
end-to-end false alarms per scan, satellite identity, or position accuracy.

## Methods and common information

All methods consume the same exact/control pilot correlation matrices, normally
14--15 supported frames by 64 consecutive symbols at 4.4 microsecond spacing.
Frequency-search methods use the same 512-point residual frequency grid. The
differential estimator quantizes its analytic phase estimate onto that same grid.
Computational differences are measured, not hidden
by giving one method additional observations or acquisition proposals.

- **Current GLRT64 margin:** maximize coherent power across symbols and sum
  powers across frames, divide by the squared-sum-of-magnitudes ceiling, then
  subtract the independently maximized rolled-template control statistic.
- **Gaussian GLRT64:** matched-subspace explained energy divided by total energy.
  The model is independent white complex Gaussian correlation noise, an unknown
  common noise scale, and an arbitrary complex signal amplitude per frame.
- **Gaussian GLRT64 margin:** the same statistic with control subtraction,
  isolating normalization changes from removal of that subtraction.
- **Adaptive normalized matched filter:** use an independently estimated full
  correlation covariance with fixed shrinkage. Account for both data and steering
  vector energy in the covariance metric. This is a plug-in adaptive statistic,
  not a claim that finite-sample covariance uncertainty has been integrated out.
- **Two 32-symbol segments:** use all 64 observations but allow independent
  complex amplitudes/phases in the two halves. The additional flexibility also
  changes the null distribution and requires its own threshold.
- **Lag-one differential:** combine adjacent-symbol phase differences as a
  shorter-coherence comparison.

The Gaussian derivation is at the correlation-matrix level. Gaussian and adaptive
variants standardize raw correlations by the square root of known per-symbol
template energy and use the corresponding square-root-energy steering vector.
The production-equivalent statistic uses unmodified raw correlations. Receiver
filtering and signal mismatch can still violate the Gaussian model; orthogonal
raw-IQ energy discarded by correlation is not available to these statistics.

## Controlled experiment

The synthetic worker freezes a machine-readable configuration before its final
evaluation, with separate seeds for covariance training, threshold calibration,
null evaluation, and injected-signal evaluation. Exact and control correlations
share a noise model derived from the sampled pilot-template Gram matrix; they
must not be represented as independent evidence from the same received waveform.

Prespecified environments are white noise, temporally colored noise, a coherent
tone interferer, and signal phase decoherence. A fixed covariance shrinkage is
used without tuning on evaluation results. Covariance estimated in the matching
environment and covariance transferred from white training are distinguished.
The synthetic template sample rate and all simplifying signal assumptions must
be recorded; synthetic thresholds are not silently transferred to hardware data.

Calibrate each method to a nominal 1% conditional false-alarm rate on calibration
nulls, then report achieved false-alarm counts and binomial uncertainty on
independent evaluation nulls. Report threshold-exceedance probability versus SNR
separately from correct-frequency acquisition. CFO errors use the circular
symbol-rate alias coordinate; report denominators and any conditioning on
detection. The unit is a fixed acquired epoch with the frequency bank maximized,
not a physical scan with data-selected timing candidates.

Sample counts may be chosen using outcome-free runtime preflight, then frozen.
No outcome-driven sample-count reduction or threshold retuning is allowed.
The primary experiment pools 14 frames per trial with a common CFO and independent
unknown frame phases. A preliminary single-frame simulation is preserved separately
as an aperture ablation. Real supported frame counts remain 14--15, not forced to
14. Each environment uses 3,000 calibration nulls, 5,000 evaluation nulls, and 600
signal trials per SNR, with 512 independent covariance-training rows.

## Recorded experiment

Use the existing DS5 server-evaluation manifest and verify each selected NPY's
hash, shape, and dtype. Selection is outcome-independent: first two real visits
per sample rate in each of development, validation, and holdout. This gives
24 visits, 48 receiver cases, and two nonoverlapping 20 ms windows per receiver
at 0 and 40 ms. The four sample rates are 2.5, 5, 7.5, and 10 MS/s. Preserve
the manifest's session-disjoint scoring splits and disclose incomplete
rate-by-edge coverage.

Covariance training uses separate third/fourth development visits per rate.
These are unlabeled RF observations, not guaranteed noise-only data; disclose
pilot/interference contamination and mismatch across rate/edge strata. No
validation or holdout observation may enter covariance training.

Use one acquisition inventory per window: the same coarse CFO domain, fine
search, candidate budget, and retained timing candidates for every scorer.
The primary replay uses the existing full `acquire_symbolwise` path with eight
retained candidates. A separate coarse-only replay isolates the earlier search
stage. Both use the same outcome-independent visit selection; their results
are separate regimes, not independent confirmation datasets.
Hash source and freeze selection/configuration before evaluating outputs. Preserve
unsupported or failed cases explicitly rather than silently dropping them.

Report scoring cost separately from shared acquisition/extraction cost, method
winner agreement, and changes in candidate timing/CFO. Same-candidate frequency
estimates from current and Gaussian GLRT64 should agree because their numerators
are identical and both denominators are frequency-independent. Cross-window
frequency consistency is descriptive: burst changes, aliases, and transmitter
switches can cause real differences. All real cases remain truth-unknown.

## Tests and review

Component-owned tests cover production-baseline equivalence, independent
white/colored likelihood oracles, identity-covariance equivalence, complex
covariance orientation, scale/phase invariance, zero/nonfinite inputs, split
separation, deterministic selection, threshold independence, and artifact hashes.

The root reviewer inspects implementation and results, reruns the combined tests,
and records limitations before writing the final report. No localization change
is made here. A subsequent position experiment must preserve observations,
candidate banks, priors and search budgets, include fitted-c versus c=0, and
separate frequency fit from position accuracy.
