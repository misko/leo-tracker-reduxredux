# Independent validation rules and physical limits

This validation covers only visits 259–263.  The frozen cache has 445 frames:
70 whose complete interpolation support ends by 20 ms, 371 whose support starts
at or after 20 ms, and four boundary-straddling frames excluded from both sets.
The implementation's 16-tap Lanczos interpolator reaches from
`floor(position)-7` through `floor(position)+8`.  Expanding both cached support
bounds by the conservative eight-sample (0.8 us) reach does not change any split
assignment; the narrowest safe margin to the 20 ms boundary is 3.20 us.

The independent checks require:

* model fitting uses only the 70 early frames and forward evaluation uses only
  the 371 held frames;
* even tones 0,2,4,6 and odd tones 1,3,5,7 remain disjoint;
* changing future observations cannot change an early forecast;
* candidate and baseline scores use their common finite support;
* residuals and uncertainty coverage use wrapped circular differences; and
* phase is unwrapped only within one contiguous visit/segment.  A missing frame
  or a visit boundary starts a new gauge rather than bridging a gap.

The odd-tone result is a differential-phase holdout, not a strict end-to-end
frequency holdout: the cached `shared_residual_hz` preprocessing estimate was
derived from RX0 using all eight tones.  Held odd-tone phases are absent from the
differential tracker fit, but odd RX0 data contributed to that shared nuisance
estimate.  This limitation must accompany any even/odd result.

## What “slow satellite phase” can mean here

The authoritative capture manifest records one Pluto radio
(`radio_pluto_5d4d`, serial ending `5d4d`), two receiver channels, 10 MS/s, and a
9.75 GHz configured LNB LO.  It does not record antenna coordinates or baseline
vector, whether the two RF paths share an LNB/LO, path cable delays, an external
reference-clock topology, satellite identity, orbit, or look direction.  Those
missing quantities prevent a numerical geometric phase-rate prediction.

The prior broadband offset audit found fitted inter-channel delays within 0.03
sample (about 3 ns), but its held-half corrected coherence was only
0.0032–0.0197.  It is therefore a weak local correlation diagnostic, not a
hardware-delay calibration.  The eight pilot tones are spaced 234,375 Hz, so a
tone-slope delay has aliases every 4.267 us.  A response normalization may test
whether a fixed per-tone phase hides a common trajectory, but cannot establish
the physical baseline or choose a delay alias from this capture alone.

Consequently, “closer to expected” is evaluated here as better held-forward
circular prediction, even-to-odd agreement, calibrated wrapped uncertainty, and
fewer unsupported/slip cases on common support.  It is not evidence of a named
satellite or proof that the remaining rate is geometric.

## Final tracker audit

The final tracker JSON parses with strict rejection of `NaN`/infinity, all six
methods report the same 371 held frames, and the CSV retains all four excluded
boundary crossers for every method. Held-tone wrapped RMS is 113.00 degrees for
frozen phase, 94.88 for an early constant-rate fit, 101.57 for the early
quadratic fit, 46.55 on 365 supported frames for the rolling robust fit (51.54
degrees when its six unsupported frames are penalized as 180-degree errors),
27.72 for previous-phase prediction, and 21.68 for the two-frame increment
baseline. The cheap causal baselines therefore outperform the proposed robust
fit on this segment; the experiment does not support promoting that fit.

Reported uncertainty widths are robust local-scatter heuristics rather than
probabilistically calibrated intervals. A descriptive frame-RMS-within-width
check covers only 24.9% of supported rolling frames (and 15.4%–65.0% for the
early models), so these widths must not be presented as confidence coverage.

Machine-readable split evidence is in `cache-audit.json`.  Synthetic regressions
are in `tests/reports/test_single_track_validation.py`; final artifact checks are
in `output-audit.json`.
