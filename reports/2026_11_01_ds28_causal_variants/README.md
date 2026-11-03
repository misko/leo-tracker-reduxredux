# DS28: fresh-cohort evaluation of causal TLE recovery variants

DS28 contains 8 fast acquisitions in [2026-10-31T14:34:49.391893+00:00, 2026-11-01T03:30:00+00:00). All are 10 Msps. 7 have usable matched baseline results; 1 remain unavailable and are retained in the roster.

The current baseline is ALGO05 (ALGO04 plus conditional gap-fragment recovery). This study reuses exact public ALGO04 exports, replays installed ALGO05, then applies the four fixed research variants from the preceding DS26/DS27 experiment. It does not re-extract IQ or rerun cold regional acquisition. No production changes were made.

## Position and native GLRT association

| Arm | Method | Mean km | Median km | P90 km | Worst km | GLRT associated | Added points |
|---|---|---:|---:|---:|---:|---:|---:|
| c0 | Current ALGO05 baseline | 0.666 | 0.464 | 1.096 | 1.368 | 75.528% | 0 |
| c0 | 48 h / ±15 s | 0.663 | 0.450 | 1.096 | 1.368 | 75.629% | 28 |
| c0 | 72 h / ±15 s | 0.663 | 0.450 | 1.096 | 1.368 | 75.629% | 28 |
| c0 | 72 h / ±30 s | 0.663 | 0.450 | 1.096 | 1.368 | 75.629% | 28 |
| c0 | 72 h / ±30 s + recency | 0.663 | 0.450 | 1.096 | 1.368 | 75.629% | 28 |
| fitted_c | Current ALGO05 baseline | 0.653 | 0.481 | 1.136 | 1.362 | 75.528% | 0 |
| fitted_c | 48 h / ±15 s | 0.650 | 0.481 | 1.136 | 1.362 | 75.629% | 28 |
| fitted_c | 72 h / ±15 s | 0.650 | 0.481 | 1.136 | 1.362 | 75.629% | 28 |
| fitted_c | 72 h / ±30 s | 0.650 | 0.481 | 1.136 | 1.362 | 75.629% | 28 |
| fitted_c | 72 h / ±30 s + recency | 0.650 | 0.481 | 1.136 | 1.362 | 75.629% | 28 |

All four variants recover the same 28 native points in **DS28-0002 RX2 CH6 T001**, assigned to NORAD **64147**. Fitted-c error changes **294.3 → 277.7 m**; c=0 changes **463.8 → 443.7 m**. The causal TLE is only **14.72 hours old**, the screening phase is about −1.8 seconds, and the minimum identity margin over the partitions and both arms is 173.76. Thus this recovery comes from the additional residual search; it does not require an older TLE, expanded phase bounds, or a recency penalty.

Across the seven usable scans, fitted-c mean error changes **652.8 → 650.4 m**, while the median (480.8 m), P90 (1,135.9 m), worst error (1,361.7 m), and four-of-seven count within 500 m remain unchanged. Native association rises from **20,937 / 27,721 (75.528%)** to **20,965 / 27,721 (75.629%)**. The c=0 mean changes 666.0 → 663.1 m. Numerical differences between the ±15 s and ±30 s accepted endpoints are below 0.1 mm.

Frequency evidence is reported separately: the recovered curve has approximately **20.2 Hz bias-profiled RMS** in the physical fit. On matched baseline support, the mean recorded negative-twice-ELBO is **2.55 higher** for fitted-c than c=0, despite its 13.22 m lower mean geographic error. This penalized score is not a raw residual RMS. The no-addition continuation changes scan 0002 error by less than 1 mm, so the 16.52 m fitted-c reduction is attributable to the added curve rather than merely continuing optimization. See `frequency-fit-ablation.json` and `trials.csv`.

**Recommendation:** retain the production default. DS28 supports a small additional recovery, but gives no incremental localization evidence for the 72-hour window, wider phase range, or recency penalty. The next useful work is the upstream failure in 0001 and the unchanged 1.362 km outlier in 0003. This cohort does not establish a general 500 m accuracy result.

## Every DS28 scan

| Scan | Status | Baseline fitted-c error, m | Recovery variants, m | Baseline GLRT | Recovery GLRT |
|---|---|---:|---:|---:|---:|
| DS28-0001 | Upstream discovery failed | — | — | Unknown | Unknown |
| DS28-0002 | Complete | 294.3 | 277.7 | 71.04% | 71.70% |
| DS28-0003 | Complete | 1361.7 | 1361.7 | 70.19% | 70.19% |
| DS28-0004 | Complete | 480.8 | 480.8 | 76.27% | 76.27% |
| DS28-0005 | Complete | 333.5 | 333.5 | 78.69% | 78.69% |
| DS28-0006 | Complete | 872.7 | 872.7 | 74.34% | 74.34% |
| DS28-0007 | Complete | 985.4 | 985.4 | 76.15% | 76.15% |
| DS28-0008 | Complete | 241.0 | 241.0 | 82.49% | 82.49% |

DS28-0001 has complete recording and GLRT inputs. A fresh, unchanged installed ALGO02 retry fails after preparation during regional discovery with `ValueError: orbit phase interpolation never extrapolates`. Consequently ALGO05 and these conditional add-ons have no qualified incumbent to extend. It remains a failed result in all five method rosters; position error and association are unknown, not zero. See `upstream-failure.json` and `upstream-failure.log`. Successful-scan metrics cover 7/8 acquisitions (87.5% availability).

![Position error distributions](position_error_distributions.png)

![Per-scan error and association](per_scan_results.png)

## Fixed experiment

The variants use 48 h / ±15 s, 72 h / ±15 s, 72 h / ±30 s, and 72 h / ±30 s with the score penalty `2 log(2) max(age_h − 48, 0) / 24`. Both element epoch and archive collection must precede the scan and meet the age bound. Existing physical nuisance priors are retained; no age-dependent prior widening is introduced.

The search covers 17 residual fragments, at most three per scan with ≥20 native points and ≥15 seconds, ranked by duration independently of position error. Complete causal STARLINK catalogues are screened at the inferred RF endpoint; up to three candidates per policy, arm and training partition receive the normalized phase/offset/rate comparison. Three seeded random 12-second block holds with 2-second guards test identity stability. The minimum score margin is 10 in every partition and both arms.

At most one new family per scan and policy is proposed. Existing-family extensions remain unchanged; at most two new families are integrated jointly. These variants are independent: a broader search can choose a different proposal and reject it, even when a narrower variant accepts its own proposal. Final position fits retain the physical orbit uncertainty model and use matched c=0/fitted-c observations, candidates, priors and budgets. A matched no-addition continuation isolates optimizer continuation from added evidence.

Both arms and controls must pass residual, phase convergence, visibility, incumbent-owner preservation, exact-orbit replay and quadrature agreement gates. Position quadrature is 0.05 s, checked at 0.025 and 0.0125 s. Rejections retain the baseline. Absolute frequency objectives across different point sets are not localization evidence. Trial objectives and control comparisons are recorded separately in the machine-readable results.

The 25 × 25 km inference box remains centered at 37.906, −122.545. The user-confirmed evaluation site (37.849061591561885, −122.48574968092912) enters only this reporting script after the inference seal. No future TLE or hand-picked satellite enters inference.

## Limits and reproduction

This is conditional recovery with a bounded shortlist and local position continuation. It does not demonstrate global satellite uniqueness or full regional reassociation. The physical model evaluates the nominated identity, rather than exhaustively reranking competitors. Eight single-site scans are a small generalization cohort.

Validation: **25 tests pass** across dataset boundaries/content identity, screening eligibility and grouped holds, normalized evidence, physical family mixtures and phase quadrature. All seven baseline selected likelihoods replay exactly; all seven fresh ALGO05 outputs match their public production decisions, positions and candidates. Every one of 10,464 nominal TLEs matches the independently exported causal catalogue. The final audit verifies 70 comparison rows, unique native IDs and preservation of every incumbent owner.

See `protocol.json`, `baseline-roster.json`, `dataset/manifest.json.gz`, `dataset-inventory.csv`, `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `decisions.csv`, `trials.csv`, and `inference-seal.json`. Every failed/unavailable scan is retained in the protocol. Native trial predictions and gate results are preserved under `position/`; [curve figures](CURVES.md) retain every attempted physical trial.

Run scripts with `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools`, and one BLAS/OMP thread. Sequence: dataset freeze; public baseline export; installed ALGO05 replay; `common.py`; `export_catalogues.py`; `screen.py preflight`; `screen.py screen`; `position.py`; `audit_replay.py`; `render.py`. The unchanged prior reconstruction implementation is imported with recorded hash, not modified.
