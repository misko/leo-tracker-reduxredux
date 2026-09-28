# Age-conditioned satellite timing prototype

## Outcome

On the 2026-09-26 12:50 UTC scan (`scan-fw-d86e8f23c0624bac`), the shared-satellite, age-prior model favors the known location over the wrong Reno location under both its uncapped predictive score and posterior-expected weighted RMS. This is a **fixed-location, fixed-identity diagnostic**, not a successful location search or proof of better generalization.

Most of the increased separation comes from sharing timing between tracks assigned to the same satellite. Age-conditioned priors add a modest effect; adding a scan-wide clock makes little difference. Individual residual fits do not uniformly improve under sharing: it restricts both sites, and the wrong site loses more flexibility.

No production code, published contracts, golden fixtures, external systems, or radio captures were changed. Sacramento/Reno geographic proposals were not shared.

## Historical calibration

- 49 archived Space-Track snapshots, all collected at least 48 hours before the target scan.
- 13 historical anchor dates, two days apart; older snapshots at approximately 6/24/48/72 hours before each anchor.
- Deterministic hash subsample of Starlink satellites, with duplicate `(satellite, old element epoch, newer element epoch)` pairs removed.
- 10,162 distinct element-epoch pairs: **8,521 training pairs from 215 satellites** and **1,641 validation pairs from 42 disjoint satellites**. Satellite-group splitting uses a deterministic hash, not a chronological split. Pairs within satellites are correlated.
- At a common epoch, project the position difference between old and newer propagated elements onto the old velocity: `tau = dot(position_new - position_old, velocity_old) / dot(velocity_old, velocity_old)`. Record the orthogonal remainder separately.
- The newer comparison elements must have age 0–24 hours. They are **not orbital truth**. This first-order orbit-space equivalent timing is a proxy for, not identical to, a receiver-Doppler time shift.
- Fit a zero-centered Student-t(4) scale using the 68th percentile of absolute historical corrections; 0.05-second floor. No target RF observations or receiver coordinates enter calibration. No satellite-specific bias is learned.

| Older element age | Training pairs | t4 scale (s) | Nominal central 90% half-width (s) | Validation coverage |
|---|---:|---:|---:|---:|
| 0–6 h | 0 | 4.151, pooled fallback | 8.85 | unavailable |
| 6–12 h | 10 | 4.151, pooled fallback | 8.85 | 2/2; insufficient |
| 12–24 h | 1,086 | 0.642 | 1.37 | 85.2% |
| 24–48 h | 2,425 | 2.030 | 4.33 | 85.1% |
| 48–72 h | 2,357 | 5.252 | 11.20 | 86.4% |
| 72–120 h | 2,643 | 10.680 | 22.77 | 84.4% |

Overall validation coverage is **85.25%, below the intended 90%**. These are useful preliminary priors, not calibrated uncertainty claims. The sample contains a negative median correction that this zero-centered model does not learn. Age >120 hours falls back to the pooled scale and is unsupported; no selected target satellite is that old.

The archive-change method supplies almost no very-young-element examples. The main arm therefore does NOT claim a calibrated tight young prior. A separate, clearly labeled sensitivity arm uses t4 scale 0.25 seconds below 12 hours (central 90% approximately +/-0.533 seconds). Its effect is small and not consistently beneficial across noise scales.

## Radio model and controls

- Same 46 tracks, original training/evaluation masks, 710 evaluation observations and 892 occupied-second track weights.
- Known receiver coordinates and original wrong-Reno coordinates are fixed. Identities are independently frozen at each site from the earlier **full-catalogue training-only zero-timing search**. There are 20 unique assigned satellites at the known site and 19 at Reno.
- This identity choice differs from the earlier reference-conditioned audit: the longest reference track is frozen to 53072, not 63850. The second-longest and third overlapping reference tracks are frozen to 63850. No identity is reselected under the new model.
- Total equivalent timing is scan clock + satellite correction. The latter is shared across all tracks assigned to that satellite. Per-track constant frequency offsets remain separate.
- Residual likelihood is normalized Student-t with 4 degrees of freedom; scales 50/100/200 Hz are prespecified sensitivity settings, **not learned from this target**. There is no satellite RMS cap and no linear drift parameter.
- At every timing grid point, fit CFO by training-only robust iterative reweighting. CFO is profiled, **not integrated**, and its uncertainty is omitted. This is therefore conditional timing integration, not a full joint Bayesian model.
- Integrate the discrete satellite timing states and optional clock state using log-sum-exp. Apply each satellite prior once per satellite, not once per track. Evaluation score is `log Z(train + evaluation) - log Z(train)` with training-fitted CFO curves held fixed. Reported timing summaries use training only.
- Observation factors assume conditional independence; temporal and inter-receiver correlation are not fully modeled. Do not turn score differences into calibrated location probabilities or odds.
- Primary numerical support below is satellite correction +/-60 seconds, 0.1-second spacing. Optional clock prior is normal, sigma 1 second, truncated at +/-3 seconds. This is a sensitivity assumption, not a clock-calibration measurement.
- The same robust CFO fitting and residual likelihood are used for every arm. Consequently the zero-offset RMS is not numerically the same as the earlier least-squares zero-offset report.

## Main comparison

At residual scale 100 Hz and satellite timing support +/-60 seconds:

| Model | Known-site predictive NLL / observation | Reno predictive NLL / observation | Known-site uncapped RMS (Hz) | Reno uncapped RMS (Hz) |
|---|---:|---:|---:|---:|
| Zero timing | 8.8675 | 8.6908 | 913.9 | 655.3 |
| Independent per-track timing, flat prior | 6.5080 | 6.6651 | 341.4 | 294.8 |
| Shared satellite timing, flat prior | 6.6617 | 7.0145 | 379.5 | 397.0 |
| Independent per-track timing, age prior | 6.5245 | 6.6706 | 342.2 | 290.0 |
| **Shared satellite timing, age prior** | **6.6588** | **7.0200** | **373.3** | **394.1** |
| Above + optional scan clock | 6.6585 | 7.0204 | 373.8 | 394.4 |
| Shared satellite + tight-young sensitivity | 6.6603 | 7.0212 | 374.0 | 393.9 |

Lower is better in all columns. RMS is the square root of the training-posterior expectation of evaluation mean-squared error, aggregated with the original occupied-second weights. It is not a best-fit residual RMS or RMS of a posterior-mean waveform.

Per-track timing still gives Reno smaller uncapped RMS while the robust predictive score prefers the reference site. Shared satellite timing makes the known site preferred by both diagnostics in this experiment. This is stronger discrimination, not uniformly cleaner residuals.

## Sensitivity and numerical checks

Known-minus-Reno predictive NLL per evaluation observation (negative favors known site), +/-60 s support:

| Residual t4 scale | Zero timing | Flat shared satellite | Age shared satellite | Age shared satellite + scan clock |
|---|---:|---:|---:|---:|
| 50 Hz | -0.0806 | -0.8006 | -0.8175 | -0.8191 |
| 100 Hz | +0.1767 | -0.3528 | -0.3612 | -0.3619 |
| 200 Hz | +0.1901 | -0.1086 | -0.1129 | -0.1136 |

- Halving or doubling all age-prior scales preserves the age-shared ranking at all three residual scales. This is sensitivity, not independent validation or parameter selection.
- At +/-30 s support and 100 Hz residual scale, refining 0.1 s to 0.05 s changes the age-shared score gap from -0.380953 to -0.380719 nats/observation. Thus 0.1 s is adequate for this comparison to about 0.00024 nats/observation, not a guarantee for all scans.
- The +/-30 s run exposed substantial boundary mass on reference track `7456360b`. Doubling support to +/-60 s changes the gap to -0.361177 without reversing the ranking. The wider result is the main table, avoiding the known clipped fit.
- This 11.43-second track prefers approximately -33.16 s at the known site (satellite 55994) and -50.60 s at Reno (49745). A young-prior sensitivity does not eliminate the alternative distant mode on wider support. Large timing corrections remain an association/model-mismatch warning even with a prior.
- In the +/-60 s age-shared arm, maximum satellite boundary-point mass is approximately 1.1e-21 at the known site and 5.4e-13 at Reno. Small endpoint mass alone does not exclude other disconnected modes beyond the searched range.
- The optional clock mean is approximately -0.68 s at the known site and -0.29 s at Reno on wider support. These are model-dependent decompositions, not measurements of clock bias.

## What this does and does not establish

Supported: a probabilistic uncapped timing model is feasible; historical uncertainty increases substantially with element age in this sample; enforcing shared satellite timing meaningfully limits independent-track flexibility at the wrong site; the known site wins under tested age-shared settings.

Not established: improved localization error from a fresh geographic search; validated satellite identities; calibrated very-young-element priors; nominal posterior coverage; a fully marginalized CFO model; robustness to observation correlation; or performance on other scans.

Next bounded experiment: include independently selected satellite alternatives at each site and marginalize identity jointly with timing. Use held-out receiver/pass groups, calibrate likelihood scale and temporal correlation outside this scan, and obtain a separate source of young-element calibration. Freeze the resulting model before independent Sacramento/Reno searches. Do not learn reference-location-specific corrections and transfer them into this evaluation.

## Artifacts and reproduction

- `probabilistic_core.py`: pure numerical prototype.
- `run_probabilistic.py`: read-only archive/input orchestration; writes only generated local report artifacts.
- `probabilistic_history.json`: all 10,162 historical pair records, source snapshot digests, split membership, fitted bins and coverage.
- `probabilistic_results.json`: 27 primary +/-30 s experiments.
- `probabilistic_results_fine.json`: three 0.05 s numerical checks at +/-30 s.
- `probabilistic_results_wide.json`: 27 +/-60 s experiments used in the main table.
- `test_probabilistic_core.py`: seven tests covering normalized density, uncertainty penalty, training-only CFO, exact latent sharing/integration, clock indexing, calibration fallback, evaluation isolation, and grid refinement invariance.

Run with the installed API Python environment and `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`:

```sh
python reports/2026_09_26_reno_track_audit/run_probabilistic.py
python reports/2026_09_26_reno_track_audit/run_probabilistic.py --step 0.05 --checks-only --suffix _fine
python reports/2026_09_26_reno_track_audit/run_probabilistic.py --bound 60 --suffix _wide
python -m pytest -q -p no:cacheprovider reports/2026_09_26_reno_track_audit/test_probabilistic_core.py reports/2026_09_26_reno_track_audit/test_nuisance_core.py reports/2026_09_26_reno_track_audit/test_scan_clock.py reports/2026_09_26_reno_track_audit/test_zero_clock.py
```

Verification: **14 tests passed**, including all seven pre-existing nuisance/clock tests. Historical fits, radio predictions, sensitivity runs and fine/wide checks completed without modifying the persisted inputs.
