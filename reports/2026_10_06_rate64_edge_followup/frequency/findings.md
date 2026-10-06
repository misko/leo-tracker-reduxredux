# Frequency-coordinate, physical Doppler and waveform-scale audit

The independent full-carrier model confirms the earlier report's **conditional
template-coordinate bias**: lower −24,857.954545 Hz, upper +31,960.227273 Hz,
upper minus lower +56,818.181818 Hz. The phase model is ideal pilot-only local-symbol
OFDM followed by a continuous mixer. This verifies the interpretation of that
model and the deployed estimator; it does not independently establish the exact
transmitter phase convention in the recorded RF, or a detector-yield fix.

![Independent CFO coordinate and alias audit](cfo-coordinate-audit.png)

The [108-case synthetic sweep](results.json) uses independently decoded Appendix-A
codes, full signed channel carriers and a continuous pilot-center mixer. It
injects zero, ±50 kHz, ±400 kHz and points ±1 kHz around both template-coordinate
alias seams at both rates and edges. Nominal tuning is zero at 2.5 MS/s and
−312.5/+312.5 kHz lower/upper at 10 MS/s. Of the 108 cases, 36 use the true
acquired CFO and 72 deliberately shift the acquired seed by ±1/Ts.

For all 36 true-seeded cases, subtracting tuning and the bias then wrapping
recovers physical CFO modulo 227,272.727273 Hz within 8.2e−9 Hz. Replacing the
legacy template by the full-carrier/mixer template gives exact score 1 and raw
tracking CFO equal to injected CFO plus nominal tuning. The legacy template
still has exact score 0.99856–0.99998 in those ideal cases. Known epoch and CFO,
no noise and ideal band isolation make these conditional estimator checks;
the ±400 kHz low-rate cases are **not** demonstrations of analog capture support.

The extra seed cases expose an important limitation of the word “alias.” Moving
the acquired seed by ±227.273 kHz changes within-symbol matching. Scores fall
to 0.0648–0.1442 and wrapped physical errors reach 99.876 kHz. Symbol-rate aliases
are equivalent for an inter-symbol phase sequence; they are not identical full
waveforms or guaranteed equivalent acquisition seeds. The source IQ and
within-symbol evidence can help distinguish branches, while a saved wrapped CFO
alone cannot recover the absolute branch.

For reporting, use this order, with `n = nominal pilot position relative to tuner
DC`, `P = 1/Ts`, and a separately justified physical alias lift `k`:

```text
physical_wrapped = wrap(raw_detector_CFO − n − b_edge, period=P)
physical_unwrapped = physical_wrapped + k × P
canonical_Doppler = physical_unwrapped × reference_RF / physical_pilot_RF
```

Subtracting `b_edge` from an already wrapped value requires another wrap. The
physical lift may differ from the old template-coordinate lift. For example,
upper physical CFO +112.636 kHz gives template-wrapped −82.676 kHz; subtracting
31.960 kHz yields −114.636 kHz, which must wrap back to +112.636 kHz. Lower physical
CFO −112.636 kHz has the complementary seam change. Physical +400 kHz and
172.727 kHz have the same wrapped coordinate. This ambiguity is mathematical,
not evidence that those full IQ waveforms are indistinguishable.

## Actual orbital frequency path

The pinned source uses neither a single channel center nor an exact edge center
for its observation normalization when tuning is displaced:

1. [scanner_tracking_source.py](../../../src/leo/storage/scanner_tracking_source.py)
   creates `actual_rf_hz = target.rf_center_hz − event.actual_if_offset_hz` for
   adaptive scans (the fixed path has the same formula).
2. [scanner_trajectory.py](../../../src/leo/application/scanner_trajectory.py)
   copies that effective tuner RF center and the **raw** tracking CFO.
3. [persistent_hop_trajectory.py](../../../src/leo/analysis/persistent_hop_trajectory.py)
   scales raw CFO and alias spacing by `11.2 GHz / actual_rf_hz`.
4. [scanner_tracking.py](../../../src/leo/application/scanner_tracking.py) passes
   that 11.2 GHz reference into the TLE matcher; the catalogue prediction bank
   computes `−RF × range_rate / c` at the reference RF.

Thus an edge difference of about 230.625 MHz is mostly represented through
normalization. At 10 MS/s, the remaining ±312.5 kHz distinction between tuner
and pilot centers is about 27–29 ppm of RF. At illustrative range rate 7 km/s,
312.5 kHz corresponds to 7.30 Hz of physical Doppler; illustrative range
acceleration 100 m/s² corresponds to 0.104 Hz/s. These are scale examples, not
measured receiver or orbit errors. Source-file SHA-256 values are in results.json.

Tuning and template-bias constants are currently scaled together with raw CFO.
An offset-only fit can absorb their constant value within a fixed lane. Correct
physical reporting should remove these terms before RF normalization and retain
an explicit physical alias choice. That change alone does not imply better
orbital RMS, satellite identity or position accuracy. Receiver clock and LNB
errors also require their own physical model; the converted CFO is not necessarily
pure satellite Doppler.

## Expected physical edge Doppler and scale mismatch

![Illustrative physical Doppler and tone dilation](doppler-and-dilation.png)

The contract's upper-minus-lower physical RF separation is **230,625,000 Hz**.
With range rate positive for recession,

```text
D_upper − D_lower = −230625000 × range_rate_m_s / 299792458
Ddot_upper / Ddot_lower = RF_upper / RF_lower  (same range acceleration)
```

At illustrative ±1 km/s, the difference is ∓769.282 Hz; at ±7 km/s it is
∓5,384.975 Hz. The slope ratio is 1.021534 on CH1 and 1.020125 on CH4.
Illustrative 100 m/s² gives upper-minus-lower slope −76.928 Hz/s. These
time-dependent physical effects are distinct from the constant +56.818 kHz
template convention. The examples do not estimate a real satellite's range rate.

A common CFO removes edge-center Doppler but cannot remove tone-dependent
frequency dilation. For illustrative 7 km/s, the scale is 23.3495 ppm and the
outer tone at ±820,312.5 Hz retains ±19.154 Hz. Over 300 symbols (1.320 ms),
this is 0.159 rad phase span and 30.82 ns of timing drift; over GLRT-64's actual
64-symbol support (0.2816 ms), it is 0.0339 rad and 6.58 ns.

The bounded analytic tone experiment compares an equal-amplitude eight-tone
fixed-CFO model with an exact time-scaled model, aligning phase at the support
midpoint. Combined coherent power losses are **0.0901% at 300 symbols and
0.00410% at 64 symbols** for that illustrative scale; the scaled template has
unit coherence. At 25 ppm the losses are 0.1033% and 0.00470%. Pure within-band
tone dilation at these scales is too small in this ideal experiment to account
for the earlier report's several-percentage-point exact-score gap.

This calculation deliberately isolates continuous tone phase; it does not model
code-transition timing, CP boundaries, analog filtering, sample-clock estimation,
multi-frame accumulation, noise or interference. Those effects can behave
differently, particularly when clock mismatch accumulates across a 20 ms probe.
It is not a measured GLRT score improvement or proof that clock skew is absent.

## Twenty-millisecond repeated-waveform stress

![Fixed-clock and known-scale synthetic stress](twenty-ms-waveform-stress.png)

The deployed conditioned estimator folds frames at fixed `fs / 750`, rounding
each frame's start to a sample, and uses fixed 4.4 µs symbol duration. A common
CFO or per-frame phase adjustment cannot correct accumulating timing drift.
At illustrative ±6 km/s, a 20.0138 ppm scale accumulates **400.277 ns across a
20 ms probe: 1.001 samples at 2.5 MS/s, 4.003 at 10 MS/s**.

The additional 12-case experiment synthesizes repeated full-carrier rectangular
OFDM under known first-order time dilation, then continuously mixes and applies
the known edge-center Doppler. It compares a fixed physical template with an
oracle that changes **the template, symbol duration and frame-folding rate**
using the injected scale. The source samples, epoch, common CFO, pilot codes
and 20 ms support remain matched. No scale is fitted to score; no receiver
calibration or acquisition claim is made. Cases at zero range rate control the
comparison. Integer frame rounding remains in both conditions, so even the
zero-scale and known-scale scores need not be exactly one.

| Rate/edge | Range rate | Fixed-clock exact | Known-scale exact | Exact-score gain |
|---|---:|---:|---:|---:|
| 2.5 MS/s lower | −6 km/s | 0.996257 | 0.998128 | +0.187 points |
| 2.5 MS/s lower | +6 km/s | 0.987366 | 0.997905 | +1.054 points |
| 2.5 MS/s upper | −6 km/s | 0.997095 | 0.997534 | +0.044 points |
| 2.5 MS/s upper | +6 km/s | 0.988665 | 0.997597 | +0.893 points |
| 10 MS/s lower | −6 km/s | 0.998073 | 0.999910 | +0.184 points |
| 10 MS/s lower | +6 km/s | 0.997082 | 0.999925 | +0.284 points |
| 10 MS/s upper | −6 km/s | 0.997980 | 0.999874 | +0.189 points |
| 10 MS/s upper | +6 km/s | 0.996664 | 0.999892 | +0.323 points |

The common CFO estimate is unchanged in every stress case. Exact evidence
improves in all eight nonzero-scale cases, with a larger recession loss at
2.5 MS/s. Margins are mixed because the rolled control score also changes.
This supports testing time-scale mismatch as a separate mechanism on saved IQ;
it does not qualify a correction or explain the observed upper-edge deficit.
The stress uses ideal sharp symbol transitions, ideal band isolation, an
initial true epoch and CH1 RF. Analog filtering, an optimized single epoch,
source clock/precompensation and interference can alter the result.

## Reproduction and tests

Run from the repository root, with the deployment snapshot accessible:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  reports/2026_10_06_rate64_edge_followup/frequency/investigate.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest discover \
  -s reports/2026_10_06_rate64_edge_followup/frequency -p 'test_*.py' -v
```

Six component-owned tests pass: independent waveform phase identity, tuning
invariance across channels/offsets, alias-lift changes at the seam, Doppler sign
and RF scaling, duration-dependent tone dilation, and correction of known time
scale in symbol timing and multi-frame folding. The run takes seconds,
uses no recording, service, database or hardware, and modifies no production
or persisted contract. No localization analysis or learned calibration is used.
