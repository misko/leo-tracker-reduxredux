This follow-up keeps the previous comparison and production sources unchanged.
Its primary input is fourteen frames of the same sixty-four normalized Qin
symbol correlations, with shared exact/control IQ projections and common CFO.
All coherent and segmented statistics search the same complete 512-bin CFO
bank. Differential comparison and longer apertures belong to the earlier
comparison or separate recorded exploration, not this primary segment test.

Natural segmented scores allow an independent complex amplitude per segment.
Exponential phase kernels are weighted quadratic statistics, not exact GLRTs;
their coherence lengths are 8, 16, and 32 symbols. Natural and exact-control
margin scores each receive independent null calibration. Margin diagnostics
are excluded from method selection. The 16/32/64 multiscale detector takes the
maximum of member scores standardized with an additional independent null
sample; its own calibration includes the multiscale search penalty. Its CFO
comes from the maximizing member. A labeled hybrid uses the identical detection
score with the sixty-four-symbol coherent CFO estimate from the same data.

The recommendation rule is frozen before development: among fixed natural
short-segment, kernel, and multiscale candidates, maximize equal-weight mean
joint detection and CFO error within 1 kHz across sigma 0.15/0.35/0.60 and rare
pi-jump stresses at -18/-15/-12/-9 dB. Each candidate must also lose at most five
percentage points of coherent detection at -15 dB versus both Gaussian coherent
and current coherent margin. Eligibility uses development point estimates;
held-out uncertainty must accompany any claim that the constraint generalizes.
If no method qualifies, the result is explicitly no short-method recommendation.
The development-selected method stays fixed during calibration and evaluation.

Each frame has an independent initial phase. Phase-stress sigma is the standard
deviation in radians of independent Gaussian symbol-to-symbol phase increments,
cumulative within each frame and reset at each frame boundary. Rare abrupt
stress independently affects each frame with probability 0.25: exactly one pi
jump at a uniform symbol boundary 1–63. The CFO truth is the common deterministic
phase slope before either phase process. Periodically wrapped CFO error avoids
alias-boundary artifacts. SNR is per normalized symbol correlator relative to
unit white Gaussian noise, excluding tone interference.

White nulls are shared among the phase scenarios because only their signals
change. Signal cases in different scenario/SNR cells use independent seeds.
AR(0.85) correlator noise and the previously specified coherent 10 dB tone are
secondary stress scenarios, excluded from recommendation selection. Their own
independent normalizers and thresholds expose conditional behavior, not transfer
of a fully frozen environment detector.

Separate seeds cover null standardization, development thresholds, development
signals, final thresholds, held-out nulls, and held-out signals. Protocol and
selection rules are persisted before development. The selected recommendation
is persisted before final calibration; thresholds are persisted before held-out
generation. Source and imported template hashes plus frozen source snapshots
are saved, and guards verify source stability before and after held-out work.
The artifacts retain all scores, CFO estimates, truths, and paired decisions.

Wilson intervals describe fixed-threshold binomial rates. Paired bootstrap
intervals describe selected-minus-baseline differences using common trials;
the aggregate bootstrap resamples within each equally weighted scenario/SNR
cell. These intervals condition on fitted thresholds and the development
selection, and do not account for calibration or selection uncertainty.

The common observed 1% ROC operating point uses held-out null thresholds solely
as a descriptive comparison. It is labeled separately from trained-threshold
performance and never changes the frozen recommendation. Oracle best segment
per cell and truth-assisted any-segment success are upper-bound diagnostics;
they are not deployable methods and receive no false-alarm claim.

This remains a conditioned correlator experiment with one correct acquired
epoch. It omits acquisition failures, within-symbol CFO attenuation, raw template
energy heteroscedasticity, and arbitrary covariance drift. Fourteen frames are
a near-production aperture; actual twenty-millisecond probes often contain
fifteen. Detection and CFO success are separate from position accuracy.

Reproduce:

```bash
.venv/bin/pytest -q reports/2026_10_07_glrt_segment_followup/test_simulation.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
.venv/bin/python reports/2026_10_07_glrt_segment_followup/simulation.py
```

The frozen development recommendation is the natural exponential phase kernel
with coherence length 32 symbols. It qualified with a two-percentage-point
coherent detection loss versus Gaussian coherent scoring in development. Kernel
16 had a slightly better unconstrained development joint objective, but failed
the coherent-sensitivity constraint. The multiscale union and its coherent-CFO
hybrid qualified but had smaller development objectives. The fixed recommendation
was not replaced by the best held-out method.

Across the sixteen prespecified phase/SNR held-out cells, selected kernel32 joint
detection and CFO success is 45.229%, versus Gaussian coherent 43.229% and current
margin 41.792%. Selected-minus-Gaussian improvement is 2.00 percentage points
(paired 95% bootstrap interval 1.64–2.38); selected-minus-current is 3.44 points
(3.00–3.85). White-null achieved rates are 1.04%, 1.06%, and 1.16%, respectively.
At the descriptive common observed 0.98% false-alarm point, joint rates are
45.073%, 42.938%, and 41.135%, so the small primary improvement persists at a
matched observed operating point. This secondary point does not retune the
trained detector. Across all methods and secondary environments, trained
false-alarm rates range from 0.60% to 1.50%.

At coherent -15 dB, selected detection is 85.67% versus Gaussian 87.50%:
-1.83 percentage points (paired 95% interval -3.33 to -0.33), within the frozen
five-point allowance. Current margin detects 83.50%; selected-minus-current is
2.17 points, with interval -0.17 to 4.33. At sigma 0.35 and -12 dB, selected
detection is 84.67% and joint success 53.83%, compared with Gaussian 73.67% and
44.00%, and current margin 66.17% and 40.00%. Gains vary across conditions;
coherent signals and mild phase stress do not uniformly improve. At sigma 0.60,
kernel32 does not maximize joint success in every cell, but remains the fixed
development-selected recommendation. The colored and tone stresses remain
poor for these unwhitened detectors; shortening phase coherence does not replace
representative covariance training.

The complete run took 15.9 seconds, used 5,000 held-out nulls per environment and
600 signals per scenario/SNR, and passed the final source guard. Five owned
simulation tests and Ruff checks pass. Results, source snapshots, scores, truths,
decisions, and paired intervals are in `simulation/final/`. The standalone
`selected_comparison.png` and `.svg` show the primary trained-threshold comparison
beside the descriptive common-null operating point, plus coherent sensitivity.
