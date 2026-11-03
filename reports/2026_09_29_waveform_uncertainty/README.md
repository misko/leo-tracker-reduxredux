# Four-visit waveform trajectories and frame sensitivity

**Superseded cross-visit convention:** this run fitted wrapped cached CFO across
visits. The localization inputs already unwrap visit-dependent frequency aliases.
See [the corrected replay](../2026_09_29_waveform_alias_audit/README.md). The original
results below remain for provenance; the corrected four-point aggregate worsens
under refinement, reversing this report's original mean-gain conclusion.

The larger test does **not** establish a broadly reliable trajectory improvement.
Long-pilot refinement improved 9/18 tracks; one DS9 track contributed 76.9% of
the pooled gain. Frame-jackknife weighting added no aggregate benefit. Keep the
cached operational baseline and do not promote this uncertainty-weighting rule.

All 106 selected excerpts were recovered and evaluated: 72 training visits and
34 held visits on 18 tracks from nine recordings. Eight frames per excerpt gives
848 demodulated frames, of which 272 supply held-visit evaluation. Two tracks
have one held visit, the others two; every track receives equal aggregate weight.
There were no extraction/numerical failures or replacements, and no main or
leave-one-frame-out frequency fit reached its search bound.

| Dataset | Tracks improved by refinement | Cached OLS NMSE | Refined OLS NMSE | Refined weighted NMSE |
|---|---:|---:|---:|---:|
| DS7 | 4/6 | 0.989822 | 0.983215 | 0.983363 |
| DS8 | 2/6 | 0.999359 | 0.995415 | 0.995828 |
| DS9 | 3/6 | 0.989232 | 0.954459 | 0.954044 |
| All | 9/18 | 0.992804 | 0.977696 | 0.977745 |

Lower held-pilot normalized mean squared error is better. The pooled OLS
reduction is 0.015108 NMSE (about 1.52% relative), but the median track reduction
is only 0.0000553. DS9 middle RX1 contributes 0.209075 to the summed reductions.
Excluding it descriptively leaves mean gain 0.003698; it is retained in every
primary aggregate. Previously reported two-point and current four-point means
are not a controlled comparison of training count: their held visits and
forecast horizons differ.

![Refinement and weighting effects](comparison.png)

## What was frozen and tested

Starting from the same 18 tracks, select four original training observations,
greedily at least one second apart, then up to two original held observations
after the last training point. Waveform quality, frequency values and previous
outcomes do not select visits. Forecast horizons range from 0.280 to 6.116 seconds.
The two short-coverage tracks are DS7 early RX1 and DS8 early RX1; neither was
replaced.

Long-pilot fitting uses symbols22–221, the first eight complete frames, independent
frame/carrier gains, the existing deterministic upconversion correction and fixed
±1500 Hz residual search. For each training excerpt, repeat the fit eight times,
leaving out one frame at a time. The jackknife standard-error proxy is
`sqrt(7/8 * sum((f_leave_one_out - mean(f_leave_one_out))**2))`.

Fit four straight-line trajectories on identical training visits:

1. Cached frequencies, ordinary least squares (OLS).
2. Refined frequencies, OLS.
3. Cached frequencies, weighted least squares (WLS).
4. Refined frequencies, WLS.

Both weighted arms use exactly `1 / max(jackknife_sigma, 25 Hz)**2`, with the
stabilizing floor fixed before results. All frequencies include actual tuned RF;
the first RF is subtracted for numerical conditioning. At held visits, compare
independent trajectory predictions against the same pilot samples, calibrating
gain on22–221 and scoring222–301. Held cached CFO defines the demodulator reference
but does not fit the trajectories. The cached-held arm is a descriptive control.

## Why this uncertainty rule is not ready

Training jackknife sigma ranges from 3.55 to 118.97 Hz, median 13.75 Hz. The
25-Hz floor applies to **59/72** training visits, so many weights are identical.
Weighted refinement is slightly worse than ordinary refinement on average by
0.0000486 NMSE. Using a descriptive 1e-10 NMSE tolerance to avoid counting
floating-point equality as success, weighting helps 6 tracks, ties8 and hurts4.
`results.json` preserves the original strict-positive counts; those count tiny
roundoff differences as wins and should not be read as meaningful improvements.

Frame removal measures sensitivity within a short excerpt. It cannot establish
absolute uncertainty or detect a bias shared by all frames, candidate/epoch
mistakes, non-linear frequency evolution, or wrong track identity. These results
do not justify treating the resulting weights as calibrated probabilities.

The local cached-held control has pooled NMSE **0.911522**, better than either
extrapolated trajectory. Refined OLS beats it on only 1/18 tracks. This rejects
replacing available per-visit measurements with this simple extrapolation rule.
It does not prove that direct per-visit long-pilot estimation is unhelpful.

## Decision for the sub-kilometer effort

Do not launch a blanket geographic replacement or tune the weighting floor on
these held results. The remaining useful question is whether the large corrections
repair specific acquisition errors that survive into the localization inputs.
Audit the exact per-visit corrections and native-to-canonical frequency mapping,
keeping the frozen candidates and observation splits. A geographic shadow test
must compare revised and cached observations on identical support and explicitly
show how sparse correction coverage limits its conclusion. This test alone is
insufficient evidence to modify the operational frequency model.

There is no verified satellite identity, external Doppler truth or position
estimate here. Existing panels have already been exposed, and upstream track
construction used full recordings. Frames are clustered within visits and tracks.
Consistent sub-kilometer accuracy remains unproven.

## Evidence and execution

- [PROTOCOL.md](PROTOCOL.md): frozen selection, fits, weights and evaluation.
- [plan.json](plan.json): 106 selections, no unsupported tracks, 32 reuse hints.
- [inventory.json](inventory.json): exact public-port candidate/source bindings and IQ hashes.
- [results.json](results.json): all training fits, 576 leave-one-frame-out fits,
  held predictions, per-frame errors and dependency hashes.
- [TABLE.md](TABLE.md): complete track comparisons and all training sensitivities.
- `prepare.py`, `extract.py`, `model.py`, `run.py`, `summarize.py`, `test_model.py`:
  reproduction and four component-owned tests.

The first extraction invocation reached its 120-second cap with 58 checkpointed
entries. The second completed the remaining48 and exited0. Reuse required exact
candidate, analysis-manifest and raw-file hash checks; all other IQ reads used
public read-only ports. Numerical evaluation exited0 within its 180-second cap.
No new RF was collected and no production code was changed.

Four tests pass: exact signed slope and offset invariance, reduced influence of
an uncertain outlier, jackknife offset invariance, and retaining short held
coverage. Ruff checks pass. Selection, inventory and result hashes are verified.
Use NumPy/SciPy and `OPENBLAS_NUM_THREADS=1` for numerical replay; Matplotlib
renders the figure. The installed read-only storage ports and local raw excerpts
are required for extraction/replay. These artifacts are local, not newly published.
