# Fixed-500-ms rate calibration and true sample-clock injection preregistration

**Frozen before this experiment read IQ or inspected new outcomes.** The exact machine-readable authority is [`fixed500-calibration-protocol-v1.json`](../config/analysis/fixed500-calibration-protocol-v1.json). This lane may use only the three digest-bound POST-FIX hard-null spans assigned to `polynomial_injection` by the deny-by-default dataset policy. It may not discover or substitute captures, open the holdout, use newer/PRE-FIX/3-or-5-MS/s data, or collect RF.

## Question and split

The experiment asks whether the unchanged causal fixed-500-ms rate point estimate can receive honest intervals under serial correlation and curvature lag, and whether a lean strict-past quadratic derivative is genuinely better. Thirty-six exact-Qin scenarios are frozen: 12 factor rows replicated on each of three backgrounds. The 18 `C` scenarios calibrate one grouped interval multiplier; the 18 `E` scenarios are evaluation-only. A whole scenario—not an overlapping endpoint—is the uncertainty unit.

All training support comes from even Qin and its rolled-Qin specificity control. Odd Qin is response-only and cannot select a frame, mask, alias, model, or multiplier. Fixed 125 ms, unchanged fixed 500 ms, calibrated fixed 500 ms, and the quadratic challenger use identical support and predeclared endpoints. Every failure and no-result row remains in the evidence ledger.

## True sample-clock model

The earlier injection changed only the phase/time coordinate. This experiment instead places physical frame `k` at `k/750` seconds, maps it to receiver sample `round(Fs × (1 + ppm×10⁻⁶) × k/750)`, and interpolates the complex Qin waveform on that scaled timebase. Carrier phase is evaluated in physical time. Thus nonzero ppm changes both waveform duration and the accumulated frame lattice.

The primary alignment uses the resulting true receiver lattice, representing a successful upstream frame-aligner and isolating rate estimation. A nominal fixed-3333/3334-lattice replay is diagnostic only. Receiver-clock rate, `physical_rate/(1+ppm×10⁻⁶)²`, is the primary truth; physical rate is secondary.

## Frozen gates

Primary scoring uses the 12 smooth, strong evaluation scenarios (`SNR ≥ −12 dB`, occupancy ≥0.70), four per background:

- all 12 and all three backgrounds must be evaluable;
- unchanged fixed-500 endpoint RMSE must be ≤250 Hz/s;
- calibrated and unchanged fixed-500 point estimates must agree numerically (RMSE ratio ≤1.000000000001);
- grouped calibrated simultaneous scenario coverage must be ≥80% overall and ≥50% on each background;
- endpoint coverage must be 80–100%, and median interval half-width ≤600 Hz/s;
- every nonzero-ppm primary row must use true waveform/lattice resampling;
- the quadratic challenger is promoted only with RMSE ≤95% of unchanged fixed 500 ms on the identical mask.

The interval multiplier is frozen as the finite-sample 95% order statistic of calibration-scenario maximum standardized endpoint errors. Because endpoint truth is instantaneous, acceleration/jerk lag from a trailing linear window is included in the calibration score rather than erased through a trailing-average estimand.

The run is bounded to 20 minutes and must stop if any background fails its frozen digest binding.
