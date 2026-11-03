# DBG01: ALGO02 on DS23-0268, the worst qualified fast scan

DS23-0268 (`fast8-auto-20261017-110835-6a38cf4c-1-upper`) is the largest position error among the **198 qualified fast recordings**, in both c arms. Fast scans without qualified positions cannot be ranked by error and remain failures in the full 207-recording fast denominator. This case was selected using evaluation error for diagnosis, not algorithm tuning or a new validation sample.

The saved ALGO02-v1 result replays exactly: **5.146 km c0 and 5.319 km fitted c**. All 81 regional starts converge within 1 cm of their respective restart solutions (a numerical spread, not physical accuracy). A diagnostic refit initialized at the reference site also returns to the displaced basin. Under this finite hypothesis pool, initialization alone does not explain the error.

The reference-site nuisance fit is worse by **34.114 / 35.003 normalized loss units**. Its curved residual RMS is only about 2.2 Hz higher. The largest global decomposition difference is approximately 25 units in grouped-noise Gamma terms. This identifies where the model preference appears; it does not establish that robust noise inference is wrong.

Removing family **53923** reduces error to about 2.1 km but fails the original paired gates. Removing **63901** gives a valid 3.7–3.9 km result. No single-family deletion or declared generic control produces a demonstrated 0.5 km solution. Several pieces of evidence influence the bias; these diagnostics do not prove that a particular satellite identity or graph join is incorrect. No GPS-picked deletion or parameter setting is promoted.

## Inputs, replay and evidence coverage

The regional prior remains a 25 × 25 km box centered at `(37.906,-122.545)`, with normal inference initialized at `(0,0)` east/north. Reference `(37.849061591561885,-122.48574968092912)` is used only for error reporting and explicitly labeled oracle diagnostics. Satellite epoch and collection timestamp both precede cutoff `1792235321735030549`; the existing causal audit checks 1402 latest, 1402 previous and 9419 historical elements for this case. No following TLE, new RF collection or IQ remeasurement enters this analysis.

Both c arms use the same **3,165 original winning GLRT observations**, **2,786 graph-owned points in 88 graph tracks**, and **1,621 curved calibration points plus 211 predictive points**. Linear evidence carries shared calibration covariance and never calibrates nuisance coefficients at a fixed position. Each arm associates **1,832 points (57.88%) in 51 tracks**. Of 1,333 unassociated winners, **954 are graph-owned** and **379 lie outside graph tracks**. Association is not equivalent to position correctness.

![Associated GLRT and tracks](associated_GLRT.png)

![Unassociated GLRT and tracks](unassociated_GLRT.png)

Gray is all winning GLRT context. Red is unassociated. Lines are graph polynomial predictions, never extra observations; unassociated lines are colored by graph track. Exact observation IDs preserve partial masks. Companion [fitted-c associated](associated_GLRT_fitted_c.png) and [unassociated](unassociated_GLRT_fitted_c.png) plots and [track membership CSV](track_membership.csv) retain both arms. Native CFO axes include receiver offsets and alias branches without a display alignment.

![Retained-track residual RMS](track_residuals.png)

[Residual diagnostics](residual_diagnostics.csv) includes profile and conditional mean/slope, quadratic BIC, step and autocorrelation tests, alias changes, visibility and maximum radio-standardized residuals. Passing these screens does not prove identity or location.

## Conditional loss and actual restart paths

![Loss and gradient](loss_gradient_10km.png)

The upper views evaluate **317 points at 1 km spacing inside the 10 km regional disk**. The lower views evaluate **289 points at 0.25 km spacing over ±2 km around the evaluation reference**. No requested pixels are outside the original box. At each pixel the original labels, aliases, curved and predictive observations stay fixed, while nuisance means, robust noise variables and five absolute-prior phase-reference updates are recomputed. This is a conditional profiled loss, not a full acquisition/association rerun or a normalized probability map. Orange arrows indicate normalized descent direction; numerical 50 m central-difference gradients at the reference and endpoint are retained in [audit.json](audit.json).

![Regional restarts](convergence_10km.png)

Every red circle is a labeled start on the 2 km grid inside the disk. Lines show recorded accepted solver steps; crosses are endpoints. Thirteen cold discoveries at 5 km spacing plus original branches provide **16 distinct whole-assignment hypotheses**. All fitted discovery positions, receiver coefficients and phases are discarded. **2 hypotheses retain the complete current predictive-family set** and enter the full-objective restart contest; **14 are excluded** because an original predictive satellite is absent from their curved state design. Those branches are not asserted to be physically impossible. Predictive identities remain fixed, curved identities/aliases can switch after each accepted c0 step, and fitted c follows the c0 branch chosen in each phase round. The objective comparison retains branch-dependent normalizations and visibility penalties. This is a finite conditional search, not exhaustive reassociation of every point against every TLE.

All 81 paired results pass the unchanged gates. Final selected branch is the incumbent for every start. The final error ranges are [5.145635931868288, 5.14563606236981] km c0 and [5.317840317027972, 5.317840599664762] km fitted c. [Restart CSV](restart_comparison.csv) stores every start, endpoint, switch count, stop reason, phase change and gate outcome. Tiny differences from the original endpoint are numerical solver-path differences, not an accuracy improvement.

## All single-family and track ablations; generic priors

All **13 active families** and **37 retained curved tracks** are individually removed and refitted in both c arms, from the same regional center with five phase rounds and 48 position steps per round. Original nuisance design and prior support remain fixed. Family deletion also removes that family's predictive tracks. Raw objectives with different observation masks are not ranked as model evidence. Geographic errors are influence diagnostics only; remaining gate failures remain visible.

![Influence and controls](influence_and_controls.png)

The track panel displays the 15 lowest-error diagnostic deletions; [interventions.csv](interventions.csv) contains every result. Red crosses mark failures of paired acceptance gates.

| Intervention | c0 error km | Fitted-c error km | Paired gates |
|---|---:|---:|---|
| 53923 | 2.058 | 2.124 | fail |
| 63901 | 3.695 | 3.880 | pass |
| 69445 | 4.773 | 4.951 | pass |
| 60415 | 4.934 | 5.027 | pass |
| 64923 | 5.026 | 5.224 | pass |
| 54873 | 5.210 | 5.366 | pass |
| 66812 | 5.345 | 5.444 | pass |
| 59328 | 5.273 | 5.446 | pass |
| 64925 | 5.256 | 5.458 | pass |
| 68343 | 5.380 | 5.547 | fail |
| 64908 | 5.877 | 5.895 | fail |
| 61977 | 6.291 | 6.336 | pass |
| 63913 | 6.472 | 6.498 | pass |

The generic controls double the current phase SD, remove its learned mean, enlarge the fragment-constant SD from 300 to 1000 Hz, reduce receiver mean drift SD from 10 to 1 Hz/s, scale the existing three orbit modes by three, or reduce smooth receiver SD from 200 to 50 Hz. Other data, priors, candidate sets and budgets remain matched. Two initial drift/smooth sensitivity outputs incorrectly changed physical design coordinates; they are preserved with `superseded_design_scaling` suffixes, explicitly excluded from all figures/tables, and rerun with latent-prior scaling. This experimental correction does not affect ALGO02 or any baseline, grid, restart, family or track result.

| Intervention | c0 error km | Fitted-c error km | Paired gates |
|---|---:|---:|---|
| baseline | 5.146 | 5.319 | pass |
| phase_x2 | 6.022 | 6.312 | pass |
| phase_zero_mean | 4.476 | 4.657 | pass |
| bias1000 | 5.479 | 5.420 | pass |
| drift1 | 4.372 | 4.503 | pass |
| orbit3 | 3.809 | 3.921 | fail |
| smooth50 | 3.978 | 4.033 | fail |

## Why the displaced position is preferred

![Objective decomposition](loss_decomposition.png)

The bars compare the fixed reference fit against the saved endpoint with nuisance and phase updates in each. Weighted data fit, all latent nuisance-prior blocks, integrated log-volume, Gamma terms, full normalization and predictive evidence close to the actual objective difference within the recorded numerical tolerance. Phase prior cost is computed about its learned mean, not about zero. This prevents a nonzero learned mean being misreported as a penalty.

[Per-track contributions](track_loss_contributions.json) show that RX1 CH1 T002 (63901) and RX1 CH5 T003 (53923) each contribute about 7–8 units of the Gamma-term preference. These are correlated, jointly fitted residuals; the table is not a calibrated test of which transmitter or receiver is wrong. A modest aggregate RMS change can carry a much larger evidence difference through several long groups.

The strongest supported diagnosis is a conditional model minimum sustained by several influential track/family constraints. The present finite association search does not overturn it. Broader complete-data association alternatives and independent radio evidence remain useful follow-ups; this report does not claim an identity fix, track-join fix, or generalizable localization improvement.

## Reproduction and validation

Use the original on-disk ALGO02 authorities and the new tools with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` and repository `.venv/bin/python`:

```text
tools/report_dbg01_algo02_ds23_0268.py --stage prepare
tools/debug_algo02_ds23_0268.py --stage audit
tools/debug_algo02_ds23_0268.py --stage discover
tools/debug_algo02_ds23_0268.py --stage bank
tools/debug_algo02_ds23_0268.py --stage analyze
tools/report_dbg01_algo02_ds23_0268.py --stage figures
```

Preserve completed outputs; use an isolated replay workspace for reconstruction. [Protocol](protocol.json) pins original inputs and initial tool hashes; [validation](validation.json) records final tool hashes, replay tolerances, counts and causal authority. [Prior correction receipt](prior_control_correction.json) records the sensitivity-only amendment. This adaptation was iteratively developed and is not claimed to be a pre-run seal of every reporting source version. Original frozen ALGO02 sources and all input hashes remain unchanged. Numeric artifacts remain local; no negative experiment is substituted into the published benchmark.
