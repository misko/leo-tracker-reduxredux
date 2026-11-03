The primary simulator compares detectors conditional on one correct acquired
epoch, pooling fourteen frames as a near-production aperture. Actual 20 ms
recorded probes contain fourteen or fifteen frames, mostly fifteen; this is
not an exact match to every recorded probe's aperture.
All methods receive the same fourteen by 64 complex exact/control symbol
correlations, permit independent unknown phases per frame, and search
the same full 512-bin residual CFO bank. CFO is common across frames. The
differential phase estimate is
quantized to that same bank. These are conditional correlator false-alarm and
detection probabilities; they do not estimate false alarms per physical scan.

Exact/control templates come from the existing sampled Qin upper-edge waveform
at 20 MHz, symbols 2–65, normalized independently to unit symbol energy. This
rate differs from the DS5 hardware corpus. Normalization removes the real raw
correlator heteroscedasticity (upper template energy max/min about 1.095 here);
the recorded replay covers actual raw template-energy variation. Their
complex per-symbol Gram overlap governs both shared Gaussian noise and signal
leakage into the rolled control. White Gaussian correlation draws are exactly
the distribution obtained by projecting the same iid complex Gaussian IQ onto
the two templates. A component test also validates explicit IQ projection.
The colored stress correlates the two orthogonal IQ noise directions across
symbols with stationary AR(1) coefficient 0.85; this is a specified correlator
covariance stress, not a measured RF power spectrum. The coherent interferer
is an actual fixed 117187.5 Hz IQ tone projected onto both template sequences,
with one random common phase per observation. Its INR is 10 dB measured as mean
exact-correlator interference power relative to unit white noise variance.

The signal is a unit-energy exact waveform in each symbol with independent
random phase per frame and uniform common trial residual CFO in ±70 kHz;
CFO phase is constant within each
symbol. This intentionally omits within-symbol CFO attenuation and timing
acquisition errors. SNR denotes signal power relative to the unit Gaussian
noise variance of one normalized symbol correlation, excluding interference.
Phase-decoherence signals add independent Gaussian phase increments with
standard deviation 0.35 radians, reset independently in each frame; their null
observations remain white. Frame noise is independent conditional on the shared
coherent tone; the tone phase evolves at the physical 750 Hz frame rate.

The complete configuration and source hashes are saved before training, and
all fitted thresholds are saved before held-out observations are generated.
Each method/environment has its own empirical 99th-percentile threshold from
3,000 independent null cases, with strict score > threshold decisions. Each
method uses the same 5,000 held-out nulls and 600 held-out signals per SNR. The
covariance estimator uses 512 additional independent null training rows and
fixed 0.25 shrinkage in each environment. A separate adaptive score using
independent white covariance training audits covariance mismatch; it still
receives an environment-specific independent false-alarm threshold. The
white-training variant transfers covariance only: its thresholds are separately
calibrated in each environment, so it is not a fully frozen detector deployment
transfer experiment. The
Gaussian exact-control margin is also retained to isolate normalization from
removing control subtraction. The optional adaptive margin is omitted because
the exact/control covariances differ under colored and tone stresses; only the
exact channel's independently fitted covariance is used for its natural score.

All detection and false-alarm rates have two-sided 95% Wilson binomial intervals.
These intervals condition on the fitted thresholds; they do not include
calibration-threshold uncertainty. Actual held-out false-alarm rates vary from
0.76% to 1.40% despite the matched nominal 1% calibration target. The thresholds
were not retuned using these outcomes. Some achieved-rate intervals exclude 1%.
CFO errors use the periodic symbol-rate alias interval. The report includes
unconditional errors on every signal draw, detection-conditional errors, and
the joint probability of detection with CFO error at most 1 kHz. Conditional
CFO summaries can be selection-biased at low detection probability; neither
frequency fit nor detection evidence establishes position accuracy.

Reproduce using:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python reports/2026_10_07_glrt_detector_comparison/synthetic.py
.venv/bin/pytest -q reports/2026_10_07_glrt_detector_comparison/test_synthetic.py
```

Primary artifacts are in `synthetic/pooled14/`. The earlier complete single-frame
run is preserved in `synthetic/single_frame_aperture_ablation/`, with its own
frozen protocol and thresholds; it tests a shorter observation aperture and
must not be presented as the production fourteen-frame detector comparison.

The primary fourteen-frame outcome gives no universal winner. The following
are held-out score exceedance rates, all using independently calibrated nominal
1% thresholds; each cell uses 600 shared signal trials:

| Environment and correlator SNR | Current margin | Gaussian exact | Trained adaptive | Segmented 32+32 | Differential |
| --- | ---: | ---: | ---: | ---: | ---: |
| White, −15 dB | 79.8% | 82.3% | 77.8% | 64.7% | 7.7% |
| AR color, −12 dB | 0.7% | 1.2% | 85.5% | 0.2% | 1.0% |
| Coherent tone, −12 dB | 1.0% | 0.3% | 100.0% | 1.7% | 0.7% |
| Phase decoherence, −12 dB | 67.5% | 72.5% | 64.2% | 79.8% | 29.8% |

At white −15 dB, the Gaussian exact-control margin detects 79.8%, identical in
aggregate to the current margin; changing the denominator alone therefore does
not explain the Gaussian exact statistic's entire modest advantage. The exact
Gaussian and current margin use achieved false-alarm rates of 0.90% and 1.10%,
respectively; independent uncertainty and the paired arrays should accompany
any inference about their difference.

Under phase decoherence at −12 dB, the joint probability of score detection and
CFO error at most 1 kHz is 39.8% current, 42.0% Gaussian, 37.7% trained adaptive,
42.8% segmented, and 2.5% differential. The segmented detector's larger score
exceedance rate does not translate proportionally into correct CFO. In the
colored and tone models, independent white-trained adaptive detection is 0.5%
and 0.3%, respectively, at −12 dB. The large adaptive gains require covariance
training representative of the specified stationary nuisance model. They do
not establish robust detection under covariance drift or arbitrary RF clutter.

`heldout_signal_scores.npz` preserves score, exact/control score, estimated
exact/control CFO, and common trial truth for every environment, SNR, and method.
`heldout_null_scores.npz` preserves whole-bank maximum null statistics.
`calibration_null_scores.npz` and `covariance_training.npz` preserve the separate
training inputs. These support paired uncertainty and descriptive held-out ROC
comparisons without turning held-out nulls into new calibration data.
The imported `templates.py` source is inherited from the repository and bound
by the companion recorded provenance; the synthetic frozen protocol hashes its
own scorer and simulator sources but does not separately hash that import.
