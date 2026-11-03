# Shorter coherent segments: detection follow-up

October 7, 2026. Three SOL workers implemented the scorers, ran independent
simulation development/evaluation, and replayed existing IQ. The root reviewer
recomputed decisions and checked recorded geometry; a separate worker checked
the saved correlations against direct numerical oracles.

**There is a modest, reproducible simulation improvement from smooth phase
weighting. A reliable improvement on recorded RF is not established.** The
development-selected exponential kernel32 improves joint detection and carrier
frequency recovery by 3.44 percentage points over the current margin detector
across the prespecified phase-stress simulations. Hard 8/16-symbol segments help
one recorded injection but lose too much coherent sensitivity to recommend as
the default. Keep kernel32 as an experimental candidate; these results do not
justify replacing the production detector.

## What changed

All prototypes and results are confined to this report directory. No production
algorithm, persisted contract, scientific fixture, or previous comparison was
changed. No RF collection was performed. The final simulation and recorded runs
took 15.9 and 76.4 seconds, respectively.

The primary simulation uses the same 64 pilot symbols in each of 14 frames,
with a shared 512-bin carrier-frequency-offset (CFO) search. Every method sees
the same observations and exact/control projections. Changing segment length
does not reduce the number of observations:

| Method | Phase-coherence assumption |
|---|---|
| Current margin | Existing 64-symbol coherent-ceiling score, exact minus control |
| Gaussian coherent | One unknown complex amplitude per frame; template-energy normalization |
| Segment8/16/32/64 | Independent complex amplitude per block; block powers summed at a common CFO |
| Phase kernel8/16/32 | Pairwise symbol products weighted by `exp(-abs(i-j)/L)` |
| Multiscale union | Maximum independently standardized segment16/32/64 score, with its own calibrated threshold |

A kernel length of 32 is a gradual correlation decay over about 141 microseconds,
not a hard 32-symbol cut. This retains nearby-symbol products across block
boundaries. The kernel is a quadratic detector, not an exact deterministic GLRT.
Exact-minus-control versions and a union with coherent CFO estimation were also
evaluated. The simulation has 19 variants; recorded replay has the 17 fixed
scorers, without the calibrated union.

## Held-out simulation

Development selected **phase_kernel32** before final calibration or evaluation.
The rule maximizes mean joint success across four phase-stress scenarios and
four SNRs, subject to at most five percentage points of coherent detection loss
at -15 dB versus both coherent baselines. Kernel16 had a higher development
objective but failed that sensitivity constraint. It was not substituted after
seeing held-out results.

Separate seeds provide 2,000 normalization nulls per environment, 3,000
development nulls, 400 development signals per cell, 3,000 final calibration
nulls per environment, 5,000 held-out nulls per environment, and 600 held-out
signals per cell. There are 16,800 held-out signals over seven scenarios and
four SNRs. Natural scores and margin diagnostics each receive their own
threshold, including the extra search in the multiscale methods.

**Joint success means detection and CFO error within 1 kHz.** The phase average
equally weights sigma 0.15/0.35/0.60 radians per symbol increment and rare pi
jumps, each at -18/-15/-12/-9 dB per normalized symbol correlation. It is an
experimental average, not an estimate of field prevalence.

| Held-out endpoint | Current margin | Gaussian coherent | Selected kernel32 |
|---|---:|---:|---:|
| Mean phase-stress joint success | 41.79% | 43.23% | **45.23%** |
| Achieved white-noise false alarms | 1.16% | 1.06% | 1.04% |
| Coherent signal detection, -15 dB | 83.50% | **87.50%** | 85.67% |
| Detection, sigma 0.35, -12 dB | 66.17% | 73.67% | **84.67%** |
| Joint success, sigma 0.35, -12 dB | 40.00% | 44.00% | **53.83%** |

The selected method's average joint gain is **+3.44 points versus current**
(paired 95% interval +3.00 to +3.85), and **+2.00 versus Gaussian coherent**
(+1.64 to +2.38). Coherent -15 dB detection loses 1.83 points versus Gaussian
(-3.33 to -0.33), within the prespecified allowance. Intervals condition on the
realized development selection and calibration; they omit uncertainty from
repeating those stages.

At a descriptive common observed 0.98% false-alarm point, phase joint success
is 41.14%, 42.94%, and 45.07%, respectively. Thus the gain is not explained just
by unequal achieved null rates. This comparison uses held-out nulls and does
not retune the operating thresholds or selected method.

Hard segment8/16/32 achieve phase joint success of 14.59%/28.27%/38.99%, and
coherent -15 dB detection of 18.00%/43.83%/69.67%. Short blocks can increase
detection under severe phase changes while sacrificing frequency resolution
and coherent sensitivity. The calibrated union achieves 43.00% phase joint
success; using coherent CFO raises it only to 43.24%. A freely chosen winner
across lengths is therefore not a cost-free improvement.

Colored AR noise and coherent-tone interference remain poor conditions for
these unwhitened detectors, even with independently calibrated conditional
thresholds. Shorter coherence is not a substitute for representative noise
modeling. These simulations also assume one correct acquired epoch, omit
within-symbol CFO attenuation, and are not end-to-end RF detection rates.
They use unit-normalized templates sampled at 20 MS/s and omit raw-correlator
energy variation; recorded replay uses actual template energies. Fourteen
simulated frames approximate the production aperture, while the recorded 20 ms
windows contain fourteen or fifteen complete frames.

![Selected-method comparison](simulation/final/selected_comparison.png)

The [SVG figure](simulation/final/selected_comparison.svg),
[complete summary](simulation/final/summary.json), and
[simulation notes](simulation_notes.md) retain all secondary comparisons.

## Recorded IQ and planted controls

The replay uses fifth/sixth visits in each DS5 rate/split block: 24 saved visits,
both receivers, 48 cases. These differ from visits scored in the prior report,
but remain part of the same existing dataset. Each first 0–20 ms window supplies
one common bank of eight acquired candidates. Each method selects a candidate
and CFO, then scores later 40–60 ms IQ at that fixed hypothesis. The later
window does not select a new timing or frequency.

Apertures of 64/128/256 symbols share complete 256-symbol frame support. Longer
apertures add observations and are a separate factor from segmentation.

There are 192 raw-IQ injection controls, balanced over development/holdout,
rates, receivers, exact/roll29 patterns, three powers, and phase sigma 0/.35.
Injected/background integrated IQ power ratios are -30/-24/-18 dB; these are
different SNR units from the normalized-correlation simulation. Acquisition is
rerun once per injected case. Recovery requires timing within one symbol and
absolute CFO error within 5 kHz. No threshold was fitted to the unlabeled RF.

| Holdout exact injection, -18 dB, 64 symbols | Current | Gaussian | Selected kernel32 | Hard segment8/16 |
|---|---:|---:|---:|---:|
| Coherent phase | 4/8 | 4/8 | 4/8 | 4/8 |
| Phase increments sigma 0.35 | 3/8 | 3/8 | 3/8 | 4/8 |

Seven of eight cases in each row have planted timing and a representable CFO
in the acquired bank. The extra hard-segment recovery is a 7.5 MS/s RX0 case
where current64 selects an alias near -512 kHz and segment8/16 select the
planted carrier near 58 kHz. Increasing aperture to 128/256 does not improve
the primary methods' recovery in these cells. At weaker injections, all methods
recover zero of eight. These small, repeated-background counts establish no
reliable real-data ranking advantage for the selected method.

The wrong-pattern stress is consequential: at -18 dB, all primary 64-symbol
methods produce positive later exact-minus-control margins on 8/8 roll29
holdout trials at both phase settings. Their nominal planted-hypothesis recovery
is zero. Roll29 can create timing ambiguity and backgrounds can already contain
real signals, so this is not a clean RF false-alarm measurement. It does show
that a positive confirmation margin alone is insufficient evidence of
specificity. Unmodified-window margin signs also have no detection-recall meaning
without truth. Full rankings and controls are in [recorded notes](recorded_notes.md)
and [recorded results](recorded/results.json).

## Validation and recommendation

All 42 follow-up tests and Ruff checks pass. The earlier comparison plus this
follow-up passes 97 tests. Tests include direct segmented least-squares and
Toeplitz quadratic oracles, nuisance invariance, template-energy normalization,
raw injection behavior, fixed later frequency,
and different simulated versus raw CFO alias policies.

The root's [independent artifact audit](verification.json) recomputes 58 score
archives, 48 development/evaluation signal cells, all 19 methods' detection/joint
counts, multiscale scores/CFOs, calibration thresholds, and the development
selection. It also checks 12,240 recorded method/aperture rankings, all injection
recovery/representability flags, the 24 input hashes, and source snapshots.
The [direct numerical audit](recorded_numerical_audit.json) verifies 144 later
kernel hypotheses and 384 baseline candidates against independent or production
oracles; maximum score error is 5.55e-17 with no frequency-bin mismatches.

The most defensible next candidate is smooth kernel32, with a calibrated
threshold and explicit frequency-quality requirement. A deployment decision
still needs representative labeled or controlled RF evidence that separates
acquisition misses, ranking errors, and false alarms. The recorded bank ceiling
and wrong-pattern results identify concrete limitations for that work. This
experiment makes no localization-accuracy claim and changes no production default.

Recheck existing artifacts without rerunning either experiment:

```bash
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python reports/2026_10_07_glrt_segment_followup/review_audit.py
.venv/bin/pytest -q reports/2026_10_07_glrt_detector_comparison \
  reports/2026_10_07_glrt_segment_followup
.venv/bin/ruff check reports/2026_10_07_glrt_segment_followup
```

[PROTOCOL.md](PROTOCOL.md) records the initial design. The more precise
[frozen simulation protocol](simulation/final/frozen_protocol.json), written
before development, adds the current-margin coherent constraint and specifies
the rare-jump probability as 0.25 per frame. The
[recorded configuration](recorded/selection.json) freezes common complete-frame
support, power levels, seeds, candidate geometry, and injection patterns.
Detailed runner commands are in the component notes.
