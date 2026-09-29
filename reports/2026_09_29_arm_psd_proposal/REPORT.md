# Power-spectrum guided GLRT: prototype and measured limits

The prototype computes a cheap raw-IQ power spectrum, ranks the eleven coarse
frequency hypotheses, and runs the full timing search and GLRT on a subset.
**The tested PSD ranking does not preserve enough original GLRT hits to replace
the current boundary-fallback method.** In particular, even the conservative
confidence gate recovers only **485/595 (81.51%) at 2.5 MS/s** in the native
replay. The current unpruned method retains 595/595 on the same inputs.

This is a saved-file research prototype. No production detector, radio
configuration, persisted contract or sealed earlier report was changed.

## What was built

- `psd_proposal.py`: eight 2048-point Hann-windowed, mean-removed FFT segments
  per receiver/window, averaged and normalized into a power spectrum. Cached
  banks compare it with shifted exact-pilot template spectra at the original
  eleven CFO bins, -400 through +400 kHz in 80 kHz steps. Two scores are tested:
  centered log-spectrum cosine and square-root power-spectrum cosine.
- `psd_probe.c`: the equivalent FFTW estimator on the actual ARM core, including
  IQ conversion, FFTs, normalization, score calculation and ranking in CPU time.
  Python and C rankings are checked on all four rates; measured ARM rankings
  and masks must agree with the recorded host estimates.
- `full_search.c` and `coarse_fp32.h`: selected CFO lanes are packed into
  four-wide SIMD groups. All original timing epochs remain; excluded frequency
  lanes are removed before peak selection. The usual eight retained candidates,
  fine search, boundary fallback and final GLRT still execute. Full-mask mode
  uses the original arithmetic path. All-rate tests cover exact selected-lane
  equality, changing masks on the same workspace, partial and zero input.
- `run_native.py` and `run_arm.py`: complete GLRT reruns and separate native PSD
  timing, with IQ, template, binary and method receipts. The global mask setter
  is research-only, serial within a process, and is not a thread-safe production
  interface.

The 11 original frequency hypotheses are coarse acquisition proposals, not
ground-truth emitter frequencies. A PSD peak alone is not a pilot detection.
No original-hit information enters spectrum estimation or mask decisions.

## Frozen selection and methods

PSD rankings were computed for all 704 saved DS7 dwells and all 680 saved
DS8/DS9 dwells: 30,448 receiver/windows across 2.5/5/7.5/10 MS/s. DS7 is the
development set. The metrics, search budgets and guard were frozen in
`method-selection.json` before DS8/DS9 feature extraction.

The guard threshold is **0.0024616268685800705**, the 90th percentile of
square-root score confidence over the 15,488 DS7 windows. It selects five
lanes only above that threshold and all eleven otherwise. This is a confidence
heuristic, not a calibrated probability of recovering every hit. The same
threshold applies to all rates; its rate dependence is part of the measured
failure. It has not been retuned on DS8/DS9.

For actual masked GLRT reruns, each dataset supplies 32 metadata-selected
dwells: four evenly spaced rows per sample rate and channel edge. That gives
**96 dwells and 2,112 overlapping 20 ms windows**, with 16,896 candidate entries
per method. This is a bounded prototype, not a full DS7/DS8/DS9 rerun. All
original baselines already exist for these exact IQ bytes.

## Actual hit recovery

The denominator is the original detector's individual positive GLRT candidates.
Matching uses the unchanged maximum-cardinality one-to-one scorer, within the
same receiver/window, <=2 samples and <=8 kHz tracking CFO, margin >=0.025.

| Method | Frequency lanes | All-rate recovered / original hits | Recovery | 2.5 MS/s recovered / original hits | Recovery |
|---|---:|---:|---:|---:|---:|
| Current boundary fallback, unpruned control | 11 | 2,535/2,536 | 99.96% | 595/595 | 100% |
| Square-root PSD ranking | 3 | 642/2,536 | 25.32% | 192/595 | 32.27% |
| Square-root PSD ranking | 5 | 1,106/2,536 | 43.61% | 304/595 | 51.09% |
| Log-PSD ranking | 9 | 2,227/2,536 | 87.82% | 497/595 | 83.53% |
| Confidence-gated five-lane search | 5 or 11 | 2,346/2,536 | 92.51% | 485/595 | 81.51% |

The one loss in the unpruned control is inherited from the previously validated
approximate boundary-fallback method; all its candidate objects exactly match
that sealed implementation on these 2,112 windows.

| Method | Original positive windows retaining a matched hit | Unmatched new positive hypotheses |
|---|---:|---:|
| Unpruned control | 993/993 | 1 |
| Three lanes | 442/993 | 99 |
| Five lanes | 651/993 | 96 |
| Nine lanes | 915/993 | 42 |
| Confidence gate | 948/993 | 7 |

These are not merely changes to candidate ordering: many originally positive
windows lose every matched hit. New unmatched positives are not assumed true
or false without independent labels.

The confidence gate prunes 86/704 DS7, 80/704 DS8 and 88/704 DS9 windows.
Its all-rate recovery is 789/843, 739/785 and 818/908 respectively. At 2.5 MS/s,
the same figures are **170/205, 104/115 and 211/275**: the DS9 transfer result is
only **76.73%**. High spectral-score confidence does not reliably mean that
omitted frequency lanes contain no useful GLRT hits. A successful narrowed
search likewise cannot certify completeness, so a no-hit-only fallback would
not guarantee the desired recovery.

`native-summary.json` contains every dataset/rate count. The earlier
`ds7-coverage.json` only describes retention of existing candidate proposals;
it is not an upper bound on actual rerun recovery because new retained
candidates can replace omitted proposals. The table above uses actual reruns.

## ARM timing scope

Four metadata-selected 2.5 MS/s dual-RX dwells were processed on CPU0 of
PLUTO+ 192.168.1.15: first lower/upper DS7, first lower DS8, and first upper DS9
within the already frozen native subsets. There are 88 windows and 90 original
positive hits. Both PSD and GLRT stages read saved CI16 into RAM before timed
work; there is no RF collection or simultaneous capture.

| Method | GLRT CPU s/dwell | PSD + GLRT CPU s/dwell | Speedup vs unpruned | Original hits recovered on ARM |
|---|---:|---:|---:|---:|
| Unpruned boundary-fallback control | 25.2159 | 25.2159 | 1.000x | 90/90 (100%) |
| Three PSD-ranked lanes | 14.4247 | 14.7075 | 1.714x | 26/90 (28.89%) |
| Five PSD-ranked lanes | 21.3397 | 21.6233 | 1.166x | 43/90 (47.78%) |
| Nine PSD-ranked lanes | 28.2305 | 28.5139 | 0.884x (slower) | 75/90 (83.33%) |
| Confidence gate: five or eleven | 23.5735 | 23.8559 | 1.057x | 69/90 (76.67%) |

The native PSD calculation costs approximately 0.283 CPU seconds/dwell, or
12.9 ms per receiver/window. The confidence gate prunes 36/88 ARM windows;
the pooled DS7 confidence threshold does not imply a 10% pruning rate at
2.5 MS/s or on a different subset. Its 1.057x throughput ratio is a 5.39%
reduction in CPU time, purchased with a 23.33% loss of original hits here.
No tested method provides the requested 90% quality/speed tradeoff.

`stage-summary.json` in each ARM folder adds separately measured PSD and GLRT
CPU times. It is not a fused pipeline's wall-clock latency. Transfer, file
loading, FFT planning and bank setup are outside the timings. The unpruned
control has no PSD overhead; every proposed narrowed method pays it. Both
PSD similarity metrics are computed in this prototype. One implementation
specialized to a single score could cost less, without repairing its recall.

Nine selected lanes still require three four-wide SIMD groups, just like the
full eleven-lane search. A reduction in logical bins is therefore not a
proportional reduction in ARM work. Timings are one serial pass over four
dwells, not a precise distribution or a locked-frequency microbenchmark.

`arm-summary.json` contains original-hit counts, all measured stage times,
exact input bindings and host/ARM comparisons. All 3,520 candidate entries
across the five ARM methods agree with their host counterparts within the
established final-field tolerances; epochs, masks and fallback decisions
agree. All 440 ARM PSD window outputs have the same log and square-root
rankings and chosen masks as Python. No ranking was corrected using baseline
outputs. Eleven Python/host tests pass; full-rate native mask units pass in
normal and ASAN/UBSAN builds, and the bounded 2.5 MS/s mask unit passes on ARM.
SOL independently reproduced the native recovery counts, the DS7-only guard
threshold and every mask, and verified the unpruned control against the
previously sealed boundary-fallback implementation.

## Interpretation and next step

The tested raw-power-spectrum model discards the coherent timing and phase
pattern used by pilot acquisition. Unknown payload/interference, receiver
passband shape and multiple GLRT hypotheses can also make spectral-shape
ranking misleading. These are plausible explanations, not separately proven
causes in this experiment. Circular shifts of a template PSD are a simplified
sampled-signal model, not a measured front-end response.

Keep the current unpruned boundary-fallback method. This prototype does not
establish an ARM improvement at >=90% individual-hit recovery for 2.5 MS/s.
A next proposal should exploit pilot or symbol/frame structure, or well-tested
causal timing/frequency information, before removing coarse hypotheses.
The experiment does not prove that all spectrum-based estimators are useless;
it rejects this raw-PSD ranking/gating approach for the current requirement.
