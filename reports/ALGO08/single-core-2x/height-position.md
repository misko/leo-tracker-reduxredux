# Estimating height jointly with horizontal Doppler position

With 120-second tracks and receivers at 1.25 or 2.25 km WGS84 height, freeing height improved horizontal error on every site and in both RF calibration arms. It also increased the held Doppler shape error in every one of those paired comparisons. With 40-second sparse tracks, the conditional uncertainty of the height estimate was about 4 km, and seven of eighteen free-height fits ended within 0.1 m of the lower optimization bound. These controlled results separate a position correction at elevated sites from evidence that a receiver can estimate its height reliably. [Pointwise results and orbit assignments](measurements/height-position.json.gz)

## Matched model and sampling

The trial verifies the same saved orbit snapshot used in the height sensitivity study and uses 11,173 Starlink records with epochs within the capture-time 48-hour bound. It uses three fixed 25 km land offers centered at 15° N, 75° E, 25° S, 65° W, and 65° N, 120° E. The evaluation draws one horizontal point within 8 km of each center on each axis. Each scenario repeats the same horizontal truth and noise realization with exact 0.10, 1.25 and 2.25 km ellipsoid heights. The optimizer receives the region, nominal orbit states and Doppler observations. It starts at the offered center and zero height. [Previous derivative study](height-sensitivity.md) · [Trial](height_position_trial.py)

The offered center alone supplies the 10° eligibility screen. The short case draws eight 40-second satellite arcs with six observations each. Five whole orbits train and three are held. The longer case draws twelve 120-second arcs with ten observations each, with eight orbits for training and four held. The truth location, orbit design and noise use separate deterministic streams. Both receivers occur in both splits. Each receiver's clock process is shared across its observations in a capture. [Frozen experiment](height_position_trial.py)

The common nuisance model integrates receiver offsets and drift, per-orbit offset and drift, and a one-second orbital phase tangent. Generated Doppler adds a 45 Hz sinusoidal clock term per receiver and 80 Hz white noise. Both height models are tested with fixed-zero RF calibration and with a fitted common RF slope. The fitted-height model adds the analytic vertical derivative at each horizontal trial point and estimates one shared height bounded to −0.5–4 km. Generation uses exact three-dimensional slant geometry and a planted RF slope of 1,170 Hz/GHz. [Model and priors](height_position_model.py)

The raw held score uses the fitted radio coefficients and marginal mean for unseen orbits. The held shape score applies a contrast derived from observation times, removing each orbit's constant and linear trend from both the measurement and prediction and dividing squared residuals by the remaining degrees of freedom. The position, height and orbit phase stay fixed for both scores. The singular-value diagnostics use local mean-geometry information with the stated nuisance priors. They give conditional uncertainty. Orbit identities and nominal trajectories are fixed.

## Horizontal error and independent Doppler

Each entry is the median across the three regions. Arrows compare fixed-zero height with fitted height. The two rightmost columns are the held shape RMS rather than in-sample scores.

| Track support | Planted height (km) | Horizontal km, `c = 0` | Horizontal km, fitted `c` | Held shape Hz, `c = 0` | Held shape Hz, fitted `c` |
|---|---:|---:|---:|---:|---:|
| 40 s | 0.10 | 5.906 → 5.939 | 2.814 → 2.848 | 78.2 → 78.3 | 77.7 → 77.7 |
| 40 s | 1.25 | 6.090 → 5.938 | 3.375 → 2.826 | 78.3 → 78.4 | 77.7 → 77.7 |
| 40 s | 2.25 | 6.260 → 5.932 | 3.900 → 2.827 | 78.4 → 78.5 | 77.8 → 77.7 |
| 120 s | 0.10 | 1.210 → 1.294 | 0.950 → 0.989 | 225.1 → 221.3 | 228.8 → 226.4 |
| 120 s | 1.25 | 1.890 → 1.294 | 1.810 → 0.987 | 210.2 → 222.0 | 212.9 → 227.2 |
| 120 s | 2.25 | 2.942 → 1.291 | 2.928 → 0.984 | 202.4 → 222.7 | 204.1 → 227.8 |

At 2.25 km with 120-second support, raw held RMS rose from 1,239 to 1,413 Hz with `c = 0` and from 1,239 to 1,503 Hz with fitted `c`, comparing medians. A held orbit's unobserved frequency offset, drift and phase contribute to these larger raw errors. Across both elevated levels the raw held error improved in six of twelve longer-track comparisons, while the affine-contrast score worsened in all twelve. The two elevated levels share each region's noise and orbit split.

The short high-latitude example gives a direct failure. At a planted height of 2.25 km, the fitted-`c` height estimate sits at −0.50 km. Freeing it worsens horizontal error from 2.62 to 2.81 km. In the longer version of that region, fitted `c` recovers 2.10 km and improves horizontal error from 2.31 to 0.23 km. Its held shape RMS increases from 238.0 to 290.6 Hz. The low-height median horizontal error also worsens when height is freed in both support designs and both calibration arms.

| Support | Median local height σ, `c = 0` / fitted (km) | Median absolute height error, `c = 0` / fitted (km) | Weakest singular value after subtracting per-orbit affines, fitted `c` (km⁻¹) |
|---|---:|---:|---:|
| 40 s | 4.01 / 4.06 | 0.60 / 0.14 | 0.012 |
| 120 s | 0.48 / 0.49 | 0.54 / 0.24 | 0.949 |

The maximum short-track height error is 2.75 km in either calibration arm. The median local height uncertainties and singular values change substantially with track duration and observation support. A low error on one short split can coexist with weak local identifiability. Free height therefore needs evidence from the actual association and nuisance problem before it can be used in publication.

All 72 fits converged. The entire experiment used 1.054 CPU seconds on one low-priority core, including 0.298 seconds for snapshot preparation. Median optimization and endpoint readout took 4.0–4.9 ms at fixed height and 4.9–5.8 ms with free height across the support and calibration groups. There were no raw replays, fresh held-out sites, or production changes. Five tests verify the whole-orbit split, affine contrasts, derivative, planted-height recovery and independence from held frequencies. [Tests](../../../tests/pipeline_eval/test_height_position_model.py)

Reproduce with `python -m reports.ALGO08.single-core-2x.height_position_trial PATH_TO_TIMESTAMP-DIGEST.tle` using the scientific release environment. The saved receipt contains the snapshot name, seed, chosen orbits, held split, observation times, per-arm position errors and CPU measurements.
