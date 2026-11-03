# DS28 revision 2: causal TLE recovery evaluation

[Findings and recommendation](FINDINGS.md): mean error 820.7 → 802.5 m, 57 recovered points, with no incremental benefit from broader TLE/phase bounds or the tested recency penalty.

DS28 contains 16 fast acquisitions in [2026-10-31T07:34:49.391893-07:00, 2026-11-01T06:39:47.024293-08:00). All are 10 Msps. 14 have usable matched baseline results; 2 remain unavailable and are retained in the roster.

The current baseline is ALGO05 (ALGO04 plus conditional gap-fragment recovery). This study reuses exact public ALGO04 exports, replays installed ALGO05, then applies the four fixed research variants from the preceding DS26/DS27 experiment. It does not re-extract IQ or rerun cold regional acquisition. No production changes were made.

## Position and native GLRT association

| Arm | Method | Mean km | Median km | P90 km | Worst km | GLRT associated | Added points |
|---|---|---:|---:|---:|---:|---:|---:|
| c0 | Current ALGO05 baseline | 0.830 | 0.729 | 1.447 | 1.864 | 74.855% | 0 |
| c0 | 48 h / ±15 s | 0.812 | 0.729 | 1.447 | 1.864 | 74.969% | 57 |
| c0 | 72 h / ±15 s | 0.812 | 0.729 | 1.447 | 1.864 | 74.969% | 57 |
| c0 | 72 h / ±30 s | 0.812 | 0.729 | 1.447 | 1.864 | 74.969% | 57 |
| c0 | 72 h / ±30 s + recency | 0.812 | 0.729 | 1.447 | 1.864 | 74.969% | 57 |
| fitted_c | Current ALGO05 baseline | 0.821 | 0.726 | 1.434 | 1.770 | 74.855% | 0 |
| fitted_c | 48 h / ±15 s | 0.803 | 0.726 | 1.434 | 1.770 | 74.969% | 57 |
| fitted_c | 72 h / ±15 s | 0.803 | 0.726 | 1.434 | 1.770 | 74.969% | 57 |
| fitted_c | 72 h / ±30 s | 0.803 | 0.726 | 1.434 | 1.770 | 74.969% | 57 |
| fitted_c | 72 h / ±30 s + recency | 0.803 | 0.726 | 1.434 | 1.770 | 74.969% | 57 |

## Physical recovery trials

| Scan | NORAD | Points | Phase bound | Decision | Candidate failures | Control failures |
|---|---:|---:|---:|---|---|---|
| DS28-0002 | 64147 | 28 | ±15 s | qualified | None | None |
| DS28-0002 | 64147 | 28 | ±30 s | qualified | None | None |
| DS28-0010 | 67579 | 29 | ±15 s | rejected | fitted_c: optimizer | fitted_c: optimizer |
| DS28-0015 | 64182 | 29 | ±15 s | qualified | None | None |
| DS28-0015 | 64182 | 29 | ±30 s | qualified | None | None |

## Every DS28 scan

| Scan | Status | Baseline fitted-c error, m | 72 h / ±30 s error, m | Baseline GLRT | 72 h / ±30 s GLRT |
|---|---|---:|---:|---:|---:|
| DS28-0001 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS28-0002 | Complete | 294.3 | 277.7 | 71.04% | 71.70% |
| DS28-0003 | Complete | 1361.7 | 1361.7 | 70.19% | 70.19% |
| DS28-0004 | Complete | 480.8 | 480.8 | 76.27% | 76.27% |
| DS28-0005 | Complete | 333.5 | 333.5 | 78.69% | 78.69% |
| DS28-0006 | Complete | 872.7 | 872.7 | 74.34% | 74.34% |
| DS28-0007 | Complete | 985.4 | 985.4 | 76.15% | 76.15% |
| DS28-0008 | Complete | 241.0 | 241.0 | 82.49% | 82.49% |
| DS28-0009 | Complete | 115.7 | 115.7 | 76.81% | 76.81% |
| DS28-0010 | Complete | 578.7 | 578.7 | 78.89% | 78.89% |
| DS28-0011 | Complete | 1213.4 | 1213.4 | 77.58% | 77.58% |
| DS28-0012 | Complete | 1769.8 | 1769.8 | 74.06% | 74.06% |
| DS28-0013 | Complete | 1464.4 | 1464.4 | 64.43% | 64.43% |
| DS28-0014 | Complete | 437.2 | 437.2 | 64.65% | 64.65% |
| DS28-0015 | Complete | 1341.5 | 1103.4 | 75.11% | 76.35% |
| DS28-0016 | Unavailable; see protocol | — | — | Unknown | Unknown |

Usable-scan metrics cover 14/16 acquisitions. Unavailable outcomes remain in the frozen roster and are not assigned zero error or zero association. Availability reasons and any failed upstream jobs are recorded in `protocol.json` and `input-availability.json`.

DS28-0001 still has the same failed public input as the previously verified ALGO02 retry: `orbit phase interpolation never extrapolates` during regional discovery. That unchanged retry evidence is retained in `upstream-evidence.json`; it was not rerun here. DS28-0016 has no published GLRT input at the availability census. Both remain unavailable across the five methods.

![Position error distributions](position_error_distributions.png)

![Per-scan error and association](per_scan_results.png)

## Fixed experiment

The variants use 48 h / ±15 s, 72 h / ±15 s, 72 h / ±30 s, and 72 h / ±30 s with the score penalty `2 log(2) max(age_h − 48, 0) / 24`. Both element epoch and archive collection must precede the scan and meet the age bound. Existing physical nuisance priors are retained; no age-dependent prior widening is introduced.

The search covers 34 residual fragments, at most three per scan with ≥20 native points and ≥15 seconds, ranked by duration independently of position error. Complete causal STARLINK catalogues are screened at the inferred RF endpoint; up to three candidates per policy, arm and training partition receive the normalized phase/offset/rate comparison. Three seeded random 12-second block holds with 2-second guards test identity stability. The minimum score margin is 10 in every partition and both arms.

At most one new family per scan and policy is proposed. Existing-family extensions remain unchanged; at most two new families are integrated jointly. These variants are independent: a broader search can choose a different proposal and reject it, even when a narrower variant accepts its own proposal. Final position fits retain the physical orbit uncertainty model and use matched c=0/fitted-c observations, candidates, priors and budgets. A matched no-addition continuation isolates optimizer continuation from added evidence.

Both arms and controls must pass residual, phase convergence, visibility, incumbent-owner preservation, exact-orbit replay and quadrature agreement gates. Position quadrature is 0.05 s, checked at 0.025 and 0.0125 s. Rejections retain the baseline. Absolute frequency objectives across different point sets are not localization evidence. Trial objectives and control comparisons are recorded separately in the machine-readable results.

The 25 × 25 km inference box remains centered at 37.906, −122.545. The user-confirmed evaluation site (37.849061591561885, −122.48574968092912) enters only this reporting script after the inference seal. No future TLE or hand-picked satellite enters inference.

## Limits and reproduction

This is conditional recovery with a bounded shortlist and local position continuation. It does not demonstrate global satellite uniqueness or full regional reassociation. The physical model evaluates the nominated identity, rather than exhaustively reranking competitors. Revision 2 retains eight previously evaluated scans and adds eight new acquisitions at the same evaluation site.

Validation receipts report dataset boundaries, causal TLE provenance, exact baseline likelihood and owner replay, and native-point integrity. Tests and exact public-baseline comparisons are recorded separately in `validation.json`, `input-audit.json`, and `tests.log`.

See `protocol.json`, `baseline-roster.json`, `dataset/manifest.json.gz`, `dataset-inventory.csv`, `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `decisions.csv`, `trials.csv`, and `inference-seal.json`. Every failed/unavailable scan is retained in the protocol. Native trial predictions and gate results are preserved under `position/`; [curve figures](CURVES.md) retain every attempted physical trial.

Run scripts with `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools`, and one BLAS/OMP thread. Sequence: dataset freeze; public baseline export; installed ALGO05 replay; `common.py`; `export_catalogues.py`; `screen.py preflight`; `screen.py screen`; `position.py`; `audit_replay.py`; `render.py`. The unchanged prior reconstruction implementation is imported with recorded hash, not modified.
