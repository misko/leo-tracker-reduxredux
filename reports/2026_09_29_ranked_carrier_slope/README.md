# Carrier-dependent phase drift does not improve the ranked waveform estimates

Do not promote the extra carrier-phase parameter. On all72 frozen ranked
excerpts, it improves later-pilot prediction in only20 cases and worsens mean
NMSE in every dataset. Its median change to the common frequency estimate is
only0.49Hz. This tested phase-drift model does not provide evidence for explaining
the larger, geographically inconsistent waveform corrections.

| Dataset | Common-frequency NMSE | Joint-model NMSE | Joint improves | Median absolute frequency change Hz |
|---|---:|---:|---:|---:|
| DS7 | 0.957382 | 0.957579 | 7/24 | 0.716 |
| DS8 | 0.936001 | 0.936399 | 6/24 | 0.337 |
| DS9 | 0.930522 | 0.930719 | 7/24 | 0.470 |
| All | 0.941302 | 0.941566 | 20/72 | 0.495 |

Lower normalized mean squared error is better. Means weight each excerpt equally;
all eight held frame scores contribute. Pooled median gain is−0.0000828 and mean
gain−0.0002641. The maximum absolute change to the common-frequency estimate is
38.81Hz. Six fits reach the±100ppm slope bound (three DS7, three DS9); all remain
in the aggregates. No fit reaches the frequency bound.

![Frequency changes versus held-pilot prediction](comparison.png)

## Hypothesis and matched comparison

A phase drift that varies with pilot-carrier frequency could be absorbed into
the single common-frequency estimator. Test this by adding one carrier-dependent
term, with predicted phase `2*pi*t*(f - offset_MHz*ppm)`. Carrier offsets are
relative to the nominal pilot-band center. The ppm coefficient describes the
measured phase slope; it is not independently calibrated as ADC clock error.
Clock effects, waveform time scaling and other propagation/model effects are
not distinguished by this parameterization alone.

The test reuses exactly the72 ranked20ms excerpts, their cached acquisition epochs
and the first eight complete frames. Both frequency models profile independent
complex gains per frame/carrier on pilot symbols22–221, and predict222–301.
There is no phase-coherence assumption between frames. The known deterministic
upconversion phase is removed as in the corrected preceding assays.

The common-frequency arm is the previously saved long-pilot fit. The joint arm
uses three fixed starts and bounds±1500Hz/±100ppm, selected by training loss only.
All216 starts qualified under the frozen optimizer/gradient criterion. The joint
training objective is at least as good as the nested common-frequency objective
in every case, but this does not transfer to held symbols. No quality threshold,
geographic result or held score selected an excerpt, fit or parameter bound.

## What this resolves

The common residual corrections in the preceding ranked experiment had median
absolute size22.71Hz and maximum411.76Hz. Allowing the tested carrier-dependent
term typically changes those estimates by less than1Hz and worsens held prediction.
This deprioritizes this particular nuisance model as a remedy. It does not prove
that all clock or timing effects are absent, nor that the common-frequency
correction is physically correct.

The median fitted slope is4.73ppm, but a fitted coefficient without predictive
support and external calibration should not be published as a receiver clock
measurement. No geographic fit was run: the frozen held-pilot gate did not
support adding this parameter. The cached operational baseline remains unchanged.
Reliable sub-kilometer accuracy remains unproven.

## Validation and evidence

The previous cached and common-frequency per-frame scores replayed within
2.23e-16. Three tests pass: signed joint recovery on synthetic pilots, analytic
gradient agreement with finite differences, and held-symbol changes leaving
the fit unchanged. All72 fits returned, with no replacement or omission.

- [PROTOCOL.md](PROTOCOL.md): frozen hypothesis, parameter bounds and evaluation.
- [results.json](results.json): every start, fitted coefficient, boundary flag,
  per-frame score, frequency shift, summary and source/code hash.
- [TABLE.md](TABLE.md): every excerpt and dataset comparison.
- `model.py`, `run.py`, `summarize.py`, `test_model.py`: implementation and tests.

Execution completed within one120-second numerical cap using NumPy/SciPy and
one BLAS thread. Matplotlib renders the figure. All IQ was already local; no
new extraction or RF collection occurred. Source hashes and Ruff checks pass.
No production code or published contract changed. Reports are local, not newly
published to remote main.
