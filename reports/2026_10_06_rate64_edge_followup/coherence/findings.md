# Saved-IQ coherence, mixer convention, and effective tone response

The continuous-mixer template gives a small timing-only improvement on most
selected strong examples, but that advantage mostly disappears when both
templates receive the same additional CFO search. Marginal examples remain
weak, noisy projections. Two 2.5 MHz upper-edge RX1 strong examples retain a
substantial physical-template deficit near the symbol-frequency alias boundary.
These results support a bounded investigation of CFO convention and effective
passband distortion; they do not establish improved detector yield, a calibrated
receiver response, or a false-alarm threshold.

## Data identity and reproducibility

The shared [experiment specification](../data/experiment-spec.json) supplies 62
selected published winners: 31 strong and 31 marginal, CH1/CH4, RX0/RX1, 2.5/10
MHz, and both edges. The original four diagnostic scans are development. Four
different scans selected by hash are evaluation. Some rate/edge/receiver lanes
have no selected example; no missing lane is imputed. Published acquisition
candidate ranks and integer epochs remain their identities. This analysis does
not reacquire the probes or search an extra set of candidate epochs.

All 62 integer and fractional exact scores, rolled-control scores, margins,
residual CFOs, and tracking CFOs reproduce within **3.33e-16** maximum absolute
error, stricter than the required 1e-7. Actual visit indexes are mapped to the
reader's retained visit indexes. Integer device counters are asserted against
the visit's valid start counter, probe start, and integer epoch. Sealed manifest
SHA-256 is independently asserted; the supported reader validates compressed
and uncompressed chunk hashes. Each result also records a probe CI16 SHA-256.
The reader is `AdaptiveHopIqStore(..., read_only=True)` against the historical
scientific source `/opt/leo-adaptive-memory/9181d637d/src`.

Primary settings were written to [results.json](results.json) before evaluation
IQ was loaded. The first full pass took **19.24 s**. The exploratory CFO
extension took **32.23 s**. There was no new RF collection, service/queue change,
storage mutation, production template change, or golden-fixture update.

## Matched template comparison

The physical template constructs the full eight-carrier OFDM symbol and then
applies a continuous pilot-band-center mixer. With absolute carrier center
`Fcenter`, symbol index `s`, prefix duration `Tg`, and symbol duration `Ts`, its
relation to the current template inside a symbol is

```text
physical(t) = current(t) * exp(-2πi * Fcenter * (s*Ts + Tg)).
```

The symbol-frequency-equivalent CFO bias is
`wrap(-Fcenter, period=1/Ts)`: **−24,857.954545 Hz lower** and
**+31,960.227273 Hz upper**. The centers are asymmetric (−492.5 versus +491.5
subcarrier spacings). Physical acquired CFO equals the saved acquired CFO minus
this bias. The production GLRT then retains its unchanged 512-cell residual-CFO
search and independent maximum for the rolled-code control.

Both templates use identical seven timing offsets
`[-2, -1, -0.5, 0, 0.5, 1, 2]` samples about the saved fractional seed, the same
first 64 pilot symbols (2–65), the same 20 ms IQ probe and available frames, and
the same selected published candidates. Each chooses its largest exact-minus-
control margin. The grids are bounded and never expanded at their boundaries;
four physical-template winners reach a ±2-sample boundary. Centering on a saved
current-template fractional seed can favor the current template and does not
prove either template's globally optimal timing. Optimizing margin on the
rolled control is itself selection, equally applied to both branches.

| Primary timing-only comparison | n | Median physical − current margin | Mean delta | Positive delta |
|---|---:|---:|---:|---:|
| Development strong | 15 | +0.009530 | +0.004678 | 14/15 |
| Evaluation strong | 16 | +0.008793 | +0.003887 | 13/16 |
| Development marginal | 16 | −0.001673 | −0.001551 | 4/16 |
| Evaluation marginal | 15 | −0.001162 | −0.000737 | 5/15 |

![Frozen timing-only template comparison](figures/template_comparison.png)

The primary trial inventory contains 62 × 2 templates × 7 timing cells = 868
target trials, plus the same 868 trials for a one-symbol-shift control. Each
trial uses the same 512-cell exact and rolled-control GLRT grids. The integer
and fractional reproduction checks add 124 unchanged scorer calls. These are
selected-candidate diagnostics, not a comparison of all top-eight candidates or
an unbiased recording-wide acquisition trial.

## Exploratory CFO extension and alias-boundary losses

After inspecting the primary development **and evaluation** results, a second
explicitly exploratory pass added acquired-CFO offsets **−20 kHz, 0, +20 kHz**
for every one of the 62 selected candidates. Every target and shifted control
under both templates receives the same 21 timing/CFO cells. All 5,208 trial
records are saved in [exploratory_cfo_results.json](exploratory_cfo_results.json);
1,736 zero-offset cells are reused from the primary pass and 3,472 new cells
are computed. This is not fresh held-out validation.

| Exploratory matched timing/CFO comparison | n | Median physical − current margin | Mean delta | Positive delta |
|---|---:|---:|---:|---:|
| Development strong | 15 | +0.000719 | −0.003713 | 11/15 |
| Evaluation strong, inspected previously | 16 | +0.000585 | −0.003198 | 10/16 |
| Development marginal | 16 | −0.000759 | −0.000838 | 5/16 |
| Evaluation marginal, inspected previously | 15 | −0.000159 | −0.000781 | 7/15 |

All 16 lower-edge strong current-template winners choose the +20 kHz acquired-
CFO boundary; 13 of 15 upper-edge strong current-template winners choose −20
kHz, with two choosing +20 kHz. The physical-template branch chooses zero CFO
offset in 24 of the 31 strong cases. The current branch's preferred shifts
largely follow the expected within-symbol convention correction. Thus a better
timing-only score does not establish that the physical waveform is intrinsically
more discriminating: much of the small gain is available through CFO adjustment
in the current template. Because many current-template optima hit the bounded
CFO grid edge, this extension does not establish globally optimized equivalence.

| 2.5 MHz upper RX1 alias-boundary example | Current timing only | Physical timing only | Current timing/CFO | Physical timing/CFO |
|---|---:|---:|---:|---:|
| Development CH4, `scan-fw-0c141ec3bab5c48e` | 0.401582 | 0.310193 | 0.448789 | 0.375085 |
| Evaluation CH1, `scan-fw-bee06eab257f2a92` | 0.430632 | 0.346475 | 0.474813 | 0.407042 |

The primary residual CFO is −112,304.6875 Hz and +112,304.6875 Hz respectively,
close to the ±113,636.3636 Hz symbol-frequency alias boundary. The development
extension changes the selected CFO alias branch, making the inferred physical
tracking CFO jump by about one symbol frequency, despite increased margin.
The evaluation case keeps its branch and improves through within-symbol CFO
adjustment. This distinguishes score recovery from a unique physical CFO
estimate. Neither example's deficit is fully removed by the small matched grid.

![Exploratory matched CFO surfaces and alias-boundary examples](figures/exploratory_cfo_alias_boundary.png)

## Empirical complex gains and time coherence

After primary physical timing/CFO correction, each useful symbol interior is
projected onto an independent eight-tone complex least-squares basis, and the
published pilot code is divided out. This uses 64 symbols per available frame;
each frame has a separately removed common phase. For each tone, within-frame
coherence is `abs(sum(gain over symbols))/sum(abs(gain over symbols))`, followed
by a median across frames. Complex gains, amplitude ratios, phase-frequency
slope, residual phase fit, and phase-time diagnostics remain available in the
row-level JSON. No continuity of absolute phase across separate frames is
assumed. The GLRT score and these gain statistics have different normalizations;
the score is not an SNR or a per-tone coherence measurement.

| Primary projection | Median tone amplitude spread | Median per-tone time coherence |
|---|---:|---:|
| Development strong | 2.56 dB | 0.330 |
| Evaluation strong | 2.80 dB | 0.357 |
| Development marginal | 10.25 dB | 0.120 |
| Evaluation marginal | 8.33 dB | 0.125 |

The eighth tone in all four selected **2.5 MHz lower-edge RX1 strong** examples
is depressed: −7.17/−9.39 dB in CH1 development/evaluation and −12.94/−11.34 dB
in CH4, relative to each example's median tone. Its time coherence is only
0.121–0.262. The 10 MHz examples show less comparable systematic loss. This is
consistent with an effective passband/projection problem at the low sample
rate, but the present captures do not identify an analog response. Pilot CFO
placement, interpolation, aliasing, symbol timing, transmitter/channel effects,
unknown payload energy, and receiver noise all remain confounded. A weak noisy
complex mean also exaggerates amplitude spread; marginal tone spread must not
be interpreted as a receiver filter curve.

The two alias-boundary outliers have 20.01 and 17.89 dB primary projected tone
spread. Exploratory CFO adjustment reduces the development spread to 11.33 dB;
the evaluation spread remains 17.88 dB. This sensitivity is direct evidence
against treating the projection as fixed analog calibration.

![Empirical tone amplitudes and within-frame coherence by lane](figures/empirical_tone_response.png)

Across all selected strong examples, the median absolute residual common
phase-time slope is 116.7 Hz, versus 1,386.5 Hz for marginal examples. A linear
phase-frequency fit gives median residual RMS phase of 0.066/0.087 rad for
development/evaluation strong examples and 0.408/0.421 rad for marginal examples.
The row-level apparent clock-drift proxy fits per-symbol phase-frequency slopes
against time. Strong examples span approximately **−426 to +508 ppm** and
marginal examples **−745 to +363 ppm**. These large, unstable values depend on
noisy phase unwrapping and finite symbol projection; they are residual
diagnostics, not credible oscillator calibration or a demonstrated clock-drift
correction. No drift/equalizer parameter is fitted back into the detector, and
no score improvement is claimed from these descriptive fits.

## Specificity controls and limits

Both templates retain the same wrong-code control (the published code rolled by
17 symbols), independently optimized over the original GLRT frequency grid.
Separately shifting each seed by one whole symbol produces another wrong-code
alignment on the same saved IQ. Those controls receive the same timing budget
as targets and the same extra CFO budget in the exploratory pass.

The largest primary optimized symbol-shift margin is **0.017383 current** and
**0.015163 physical**. With the exploratory CFO extension, the largest is
**0.021482 current** and **0.017376 physical**. All remain below the published
0.025 gate. The largest physical marginal-example margin is 0.017245 primary
and 0.018266 exploratory, also below the gate. Strong examples retain clear
target-versus-control separation, while the marginal examples remain in the
same small-margin range as these negative alignments.

![Projection diagnostics and matched symbol-shift controls](figures/coherence_and_controls.png)

These 62 selected candidates and single shifted alignment per seed are too
small and too selected to calibrate false alarms or estimate detector yield.
No noise-only dataset or exhaustive wrong-code inventory is claimed. There are
no localization conclusions; these are waveform, CFO, and projection checks.

## Reproduction commands and checks

Run from the repository root. Corpus access requires the existing elevated
read identity; outputs stay in the report directory. Historical-source imports
remain fixed in both runs. Set `PYTHONDONTWRITEBYTECODE=1` and limit BLAS/OMP to
one thread.

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH=/opt/leo-adaptive-memory/9181d637d/src \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  reports/2026_10_06_rate64_edge_followup/coherence/analyze.py \
  --spec reports/2026_10_06_rate64_edge_followup/data/experiment-spec.json \
  --output reports/2026_10_06_rate64_edge_followup/coherence/results.json

sudo -n env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH=/opt/leo-adaptive-memory/9181d637d/src \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  reports/2026_10_06_rate64_edge_followup/coherence/explore_cfo.py \
  --spec reports/2026_10_06_rate64_edge_followup/data/experiment-spec.json \
  --primary reports/2026_10_06_rate64_edge_followup/coherence/results.json \
  --output reports/2026_10_06_rate64_edge_followup/coherence/exploratory_cfo_results.json

env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  reports/2026_10_06_rate64_edge_followup/coherence/plot.py

env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH=/opt/leo-adaptive-memory/9181d637d/src \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  -m unittest discover \
  -s reports/2026_10_06_rate64_edge_followup/coherence -p test_analyze.py -v
```

Three report-owned independent analytic tests pass: full-carrier construction
followed by continuous mixing; the symbol-phase identity and exact asymmetric
CFO biases; and recovery of known eight-tone gain spread/time coherence from
synthetic clean IQ. The synthetic test validates the projection calculation,
not the physical interpretation of the measured corpus coefficients. See
[summary.json](summary.json) for aggregates and [analyze.py](analyze.py),
[explore_cfo.py](explore_cfo.py), and [plot.py](plot.py) for complete recipes.
