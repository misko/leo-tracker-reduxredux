# DS25 same-interval fast comparison: causal TLE recovery variants

[Results, interpretation and recommendation](FINDINGS.md): 62 extra points, no measured localization improvement; retain the current default.

DS25 itself contains adaptive scans only. At the user's confirmation, this study evaluates its **34 same-interval fast comparison scans**, retaining their original DS24 identifiers. The frozen interval is [2026-10-21T16:42:37-07:00, 2026-10-24T07:38:14-07:00). All are 10 Msps. 25 have usable matched baseline results; 9 remain unavailable and are retained in the roster.

The current baseline is ALGO05 (ALGO04 plus conditional gap-fragment recovery). This study reuses frozen ALGO02/03 evidence, runs installed ALGO04 and ALGO05, then applies the four fixed research variants from the DS26/DS27 and DS28 experiments. Historical failed process audits receive one bounded ALGO03 retry. It does not re-extract IQ or rerun cold regional acquisition. No production changes or dataset renaming were made.

The historical DS25 fast comparison reported 24 usable acquisitions. The refreshed public-input census finds GLRT inputs for 25, including DS24-0010; DS24-0001 through DS24-0009 have no existing public GLRT input. This is a fresh comparison of the current baseline and fixed variants on available evidence, not a reproduction of the old position-error table.

DS24-0091 exhausted its bounded ALGO03 retry with 37 of 38 process receipts accounted for. Its original ALGO02 position has a complete audit and is preserved unchanged through the installed ALGO04/05 fallback envelopes. That verified incumbent remains in all five methods and both c arms; no recovery candidate from the failed audit is used. It is explicitly marked recovery unavailable, rather than removed from the position distribution.

## Position and native GLRT association

| Arm | Method | Mean km | Median km | P90 km | Worst km | GLRT associated | Added points |
|---|---|---:|---:|---:|---:|---:|---:|
| c0 | Current ALGO05 baseline | 1.162 | 1.024 | 2.000 | 2.188 | 72.727% | 0 |
| c0 | 48 h / ±15 s | 1.162 | 1.024 | 2.000 | 2.188 | 72.727% | 0 |
| c0 | 72 h / ±15 s | 1.162 | 1.024 | 2.000 | 2.188 | 72.782% | 62 |
| c0 | 72 h / ±30 s | 1.162 | 1.024 | 2.000 | 2.188 | 72.782% | 62 |
| c0 | 72 h / ±30 s + recency | 1.162 | 1.024 | 2.000 | 2.188 | 72.782% | 62 |
| fitted_c | Current ALGO05 baseline | 1.175 | 1.017 | 2.013 | 2.205 | 72.727% | 0 |
| fitted_c | 48 h / ±15 s | 1.175 | 1.017 | 2.013 | 2.205 | 72.727% | 0 |
| fitted_c | 72 h / ±15 s | 1.175 | 1.017 | 2.013 | 2.205 | 72.782% | 62 |
| fitted_c | 72 h / ±30 s | 1.175 | 1.017 | 2.013 | 2.205 | 72.782% | 62 |
| fitted_c | 72 h / ±30 s + recency | 1.175 | 1.017 | 2.013 | 2.205 | 72.782% | 62 |

## Recovery decisions and numerical gates

| Scan | NORAD | Points | Phase bound | Decision | Failed candidate gates | Failed control gates |
|---|---:|---:|---:|---|---|---|
| DS24-0019 | 69445 | 53 | ±30 s | rejected | None | c0: optimizer |
| DS24-0077 | 100418 | 34 | ±15 s | rejected | None | c0: optimizer |
| DS24-0077 | 100418 | 34 | ±30 s | rejected | None | c0: optimizer |
| DS24-0079 | 63045 | 62 | ±15 s | qualified | None | None |
| DS24-0079 | 63045 | 62 | ±30 s | qualified | None | None |
| DS24-0083 | 67624 | 27 | ±15 s | rejected | c0: optimizer | c0: optimizer, c0: incumbent_exact_orbits, c0: existing_owners_preserved, fitted_c: optimizer |
| DS24-0083 | 67624 | 27 | ±30 s | rejected | c0: optimizer | c0: optimizer, c0: incumbent_exact_orbits, c0: existing_owners_preserved, fitted_c: optimizer |

An optimizer-only rejection means the solver did not declare successful convergence. It is not evidence that the satellite failed the residual or visibility checks. A failed matched control also prevents promotion, even when the candidate fit passes. These fixed gates were not relaxed after seeing position errors.

9 distinct screened fragments were excluded because their nominated satellite already belongs to the baseline. Existing-family extension is unchanged in this experiment; those exclusions are not failed satellite-fit tests.

| Scan | Fragment | Existing NORAD |
|---|---|---:|
| DS24-0010 | 014b4a81360acf92128d | 63069 |
| DS24-0012 | 00280c579a35b5c2ee1f | 64121 |
| DS24-0015 | 0b79ed005807cac703a9 | 59843 |
| DS24-0075 | 5332721e3afbb13948a9 | 66226 |
| DS24-0075 | 9ecf4239ac861fcf8897 | 66226 |
| DS24-0085 | 275c6c069c98b8a95039 | 62806 |
| DS24-0085 | 73f2415739794e2f8d75 | 62806 |
| DS24-0089 | 83f83d08d1fa6a5b295a | 59328 |
| DS24-0097 | c866bd900e1d08ecc788 | 68711 |

## Every fast comparison scan

| Scan | Status | Baseline fitted-c error, m | 72 h / ±30 s error, m | Baseline GLRT | 72 h / ±30 s GLRT |
|---|---|---:|---:|---:|---:|
| DS24-0001 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0002 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0003 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0004 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0005 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0006 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0007 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0008 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0009 | Unavailable; see protocol | — | — | Unknown | Unknown |
| DS24-0010 | Complete | 1274.3 | 1274.3 | 75.82% | 75.82% |
| DS24-0011 | Complete | 1666.8 | 1666.8 | 60.84% | 60.84% |
| DS24-0012 | Complete | 1851.8 | 1851.8 | 77.20% | 77.20% |
| DS24-0013 | Complete | 857.2 | 857.2 | 79.43% | 79.43% |
| DS24-0014 | Complete | 509.0 | 509.0 | 73.13% | 73.13% |
| DS24-0015 | Complete | 1725.6 | 1725.6 | 61.23% | 61.23% |
| DS24-0016 | Complete | 586.6 | 586.6 | 77.20% | 77.20% |
| DS24-0017 | Complete | 1935.7 | 1935.7 | 78.52% | 78.52% |
| DS24-0018 | Complete | 1018.0 | 1018.0 | 77.79% | 77.79% |
| DS24-0019 | Complete | 1016.8 | 1016.8 | 54.15% | 54.15% |
| DS24-0075 | Complete | 1096.2 | 1096.2 | 73.53% | 73.53% |
| DS24-0077 | Complete | 1266.5 | 1266.5 | 75.41% | 75.41% |
| DS24-0079 | Complete | 877.9 | 885.1 | 65.29% | 66.67% |
| DS24-0081 | Complete | 2065.0 | 2065.0 | 69.67% | 69.67% |
| DS24-0083 | Complete | 346.3 | 346.3 | 77.75% | 77.75% |
| DS24-0085 | Complete | 877.4 | 877.4 | 76.68% | 76.68% |
| DS24-0087 | Complete | 1713.1 | 1713.1 | 81.82% | 81.82% |
| DS24-0089 | Complete | 2205.2 | 2205.2 | 63.04% | 63.04% |
| DS24-0091 | Verified incumbent retained; recovery unavailable | 923.4 | 923.4 | 74.07% | 74.07% |
| DS24-0093 | Complete | 768.0 | 768.0 | 87.05% | 87.05% |
| DS24-0095 | Complete | 377.1 | 377.1 | 57.38% | 57.38% |
| DS24-0097 | Complete | 835.5 | 835.5 | 77.40% | 77.40% |
| DS24-0099 | Complete | 678.0 | 678.0 | 77.36% | 77.36% |
| DS24-0101 | Complete | 2121.4 | 2121.4 | 69.93% | 69.93% |
| DS24-0103 | Complete | 786.5 | 786.5 | 76.44% | 76.44% |

All 34 requested fast scans remain in the roster. A missing GLRT or unqualified upstream result is not assigned zero position error or zero association. Usable-scan distributions cover 25/34 acquisitions; exact unavailable reasons are retained in `protocol.json` and the public-input availability audit.

![Position error distributions](position_error_distributions.png)

![Per-scan error and association](per_scan_results.png)

## Fixed experiment

The variants use 48 h / ±15 s, 72 h / ±15 s, 72 h / ±30 s, and 72 h / ±30 s with the score penalty `2 log(2) max(age_h − 48, 0) / 24`. Both element epoch and archive collection must precede the scan and meet the age bound. Existing physical nuisance priors are retained; no age-dependent prior widening is introduced.

The search covers 70 residual fragments, at most three per scan with ≥20 native points and ≥15 seconds, ranked by duration independently of position error. Complete causal STARLINK catalogues are screened at the inferred RF endpoint; up to three candidates per policy, arm and training partition receive the normalized phase/offset/rate comparison. Three seeded random 12-second block holds with 2-second guards test identity stability. The minimum score margin is 10 in every partition and both arms.

At most one new family per scan and policy is proposed. Existing-family extensions remain unchanged; at most two new families are integrated jointly. These variants are independent: a broader search can choose a different proposal and reject it, even when a narrower variant accepts its own proposal. Final position fits retain the physical orbit uncertainty model and use matched c=0/fitted-c observations, candidates, priors and budgets. A matched no-addition continuation isolates optimizer continuation from added evidence.

Both arms and controls must pass residual, phase convergence, visibility, incumbent-owner preservation, exact-orbit replay and quadrature agreement gates. Position quadrature is 0.05 s, checked at 0.025 and 0.0125 s. Rejections retain the baseline. Absolute frequency objectives across different point sets are not localization evidence. Trial objectives and control comparisons are recorded separately in the machine-readable results.

The 25 × 25 km inference box remains centered at 37.906, −122.545. The user-confirmed evaluation site (37.849061591561885, −122.48574968092912) enters only this reporting script after the inference seal. No future TLE or hand-picked satellite enters inference.

## Limits and reproduction

This is conditional recovery with a bounded shortlist and local position continuation. It does not demonstrate global satellite uniqueness or full regional reassociation. The physical model evaluates the nominated identity, rather than exhaustively reranking competitors. This is a single-site cohort, and previously studied DS24 data are not an untouched generalization set.

Validation receipts cover exact baseline objective/ownership replay, causal catalogue provenance, unchanged nominal elements, unique native IDs and component tests. See `validation.json`, `input-audit.json`, `full-replay-audit.json`, and `numerical-provenance.json`.

See `protocol.json`, `baseline-roster.json`, `dataset/manifest.json.gz`, `dataset-inventory.csv`, `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `decisions.csv`, `trials.csv`, and `inference-seal.json`. Every failed/unavailable scan is retained in the protocol. Native trial predictions and gate results are preserved under `position/`; [curve figures](CURVES.md) retain every attempted physical trial.

Run scripts with `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools`, and one BLAS/OMP thread. Sequence: `prepare.py`; `run_baselines.py` using pinned installations; `finalize_baselines.py`; `common.py`; `export_catalogues.py`; `screen.py preflight`; `screen.py screen`; `position.py`; `audit_inputs.py`; `audit_replay.py`; `render.py`; `validate_results.py`. Public-input inventory and adapter tests are recorded separately. The unchanged prior reconstruction implementation is imported with recorded hash, not modified.
