# Roof receiver-direction evaluation

## Outcome

**Arrival-direction features improve reception prediction on all four held-out roof scans.** This is a positive directional-feasibility result at the known roof position, **not a measured geographic-error improvement**.

SOL implemented and ran the Doppler-only direction extraction and reception models; a second SOL review audited the experiment and artifacts. Main-agent checks resolved exact source links, verified controls, and ran the final evaluation. No new RF collection, production change, or source-data mutation was performed.

| Held-out endpoint, equal weight per track | M0: sensitivity baseline | M1: add direction | Relative loss reduction |
|---|---:|---:|---:|
| Compatible counterpart detection: log loss | 0.65337 | 0.47909 | 26.7% |
| Matched log(GLRT-margin RX1/RX0): mean squared error | 0.32169 | 0.17381 | 46.0% |

The second row is **MSE of a log detection-margin ratio**, not RF-power error, Doppler RMS, or position error.

## Corpus and selection

Twenty-seven roof pose companions were available at the initial inventory. The newest twelve formed a preserved freshness panel; only five calibration and one test analysis were complete at that inventory. Before reception scoring, a separate readiness-only cohort selected the newest ten complete analyses among the same capture-time cutoff. The first six calibrate and final four test. This amendment is recorded in `PROTOCOL.md` and `evaluation_manifest.json`; no scan was selected by signal quality or location error. The 02:50 analysis completed between the two inventories, which remain preserved separately.

| UTC start, 2026-09-27 | Session | Split | MS/s |
|---|---|---|---:|
| 02:07 | `scan-fw-c559f436d578c9bd` | calibration | 10 |
| 02:14 | `scan-fw-39ac2b14d1bb5f0f` | calibration | 10 |
| 02:21 | `scan-fw-aa9770c66396e928` | calibration | 2.5 |
| 02:28 | `scan-fw-9d7b6a0db558703a` | calibration | 2.5 |
| 02:35 | `scan-fw-da2858f6cd2521b7` | calibration | 10 |
| 02:42 | `scan-fw-4c56320fb5ca6994` | calibration | 7.5 |
| 02:50 | `scan-fw-00ff81dc09fc738a` | held out | 10 |
| 03:04 | `scan-fw-898b709fcf3dd978` | held out | 5 |
| 03:11 | `scan-fw-3ebf3526172258af` | held out | 5 |
| 03:25 | `scan-fw-851486cc2a1acd99` | held out | 2.5 |

All ten have complete public tracking inputs and verified pose/source bindings. There are 599 tracks and 25,323 source observations. The reception endpoint uses only the 10,369 observations excluded from their track's Doppler-fitting mask: 6,617 calibration / 3,752 test, across 354 / 245 tracks. All observations resolved uniquely through public candidate/tracklet provenance; no ambiguous join was silently chosen. Propagation UTC and source support-center UTC agree exactly: maximum discrepancy **0 ns**.

The pose remains operator-supplied WGS84 roof coordinates, nominal opposite east/west tilts, and provisional receiver mapping—not a verified GPS survey. Altitude, world tilt, RF phase centers and antenna gain patterns remain unmeasured. Zero altitude was an explicit propagation approximation.

## What was fitted

- Satellite hypotheses: causal on-disk TLE catalogue, known roof position, zero timing correction, independent per-track constant frequency offset, training-frequency residual SSE, top-three candidate weights at a fixed 100 Hz scale. Cross-receiver reception outcomes do not select satellite identity. These truncated weights are not calibrated satellite probabilities.
- Primary endpoint: given a detected anchor on one RX, predict a compatible counterpart on the other RX in the same observed probe. Compatibility uses the earlier fixed 2.2 microsecond modulo-frame / 10 kHz CFO tolerances. Counterpart selection uses frequency/epoch proximity, not maximum margin.
- M0: channel×edge sensitivity, receiver, sample-rate category, and log anchor margin. M1 adds the signed east component of the Doppler-weighted arrival direction. Both use the same fixed ridge strength, with calibration-only scaling/fitting.
- Secondary endpoint: log(RX1 margin / RX0 margin), conditional on both candidates being detected and compatible. M0 uses the same categorical nuisances; M1 adds east direction. It is a censored detection-proxy experiment, not a calibrated antenna-power fit.
- A track contributes unit total weight. Frames and reciprocal receiver anchors are not claimed to be independent. Track construction still depends on GLRT-gated candidate selection even though the scored observations are excluded from Doppler fitting.

## Held-out scan results

| UTC | Detection M0 | Detection M1 | Ratio MSE M0 | Ratio MSE M1 |
|---|---:|---:|---:|---:|
| 02:50 | 0.64202 | 0.38372 | 0.28626 | 0.12267 |
| 03:04 | 0.68147 | 0.47982 | 0.31026 | 0.14000 |
| 03:11 | 0.61065 | 0.53480 | 0.23353 | 0.17503 |
| 03:25 | 0.68184 | 0.51715 | 0.48077 | 0.26999 |

The coefficient sign is consistent with increasing relative RX1 response toward inferred east, under the recorded provisional mapping. This does not independently survey the physical antenna axes.

## Controls and sensitivity checks

- **Matching:** 3,003/8,867 held-out visits have compatible candidates on both RXs; the channel/edge-preserving long-time shift gives **0/8,867**. Compatibility is not decoded satellite identity.
- **Receiver CFO nuisance:** candidate-pair-weighted bias 2,380.14 Hz; one-vote-per-probe sensitivity 2,381.95 Hz. The 1.81 Hz difference is negligible relative to the frozen 10 kHz window.
- **Test rates represented in calibration only:** exclude the two 5 MS/s test scans, without refitting. Detection loss **0.66193 → 0.45044**; ratio MSE **0.37524 → 0.19006**.
- **Tracks lasting ≥30 seconds:** 148 tracks / 4,307 endpoint observations across calibration and test. Refit the same models under this predeclared eligibility rule. Detection **0.63637 → 0.40058**; ratio MSE **0.32950 → 0.16848**. Every test scan still improves.
- **One physical pair, one ratio measurement:** remove 242 reciprocal duplicate rows, giving 6,043 unique pairs from 6,285 matched anchors. Refit/score the secondary model under this rule: **0.31861 → 0.17227**.

Fixed-coefficient direction controls:

| Direction treatment | Detection M1 loss | Ratio M1 MSE |
|---|---:|---:|
| Actual test directions | 0.47909 | 0.17381 |
| One calibration-direction permutation, then refit | 0.62087 | 0.28960 |
| One within-test-scan trajectory shuffle | 0.94192 | 0.44356 |
| Reverse mapping with learned coefficients held fixed | 1.49056 | 0.69763 |

The calibration permutation retains a smaller improvement; it is not represented as a perfect null or a permutation p-value.

### Additional post-result robustness audit

`stricter_controls.json` records checks added after the primary result, without tuning the frozen settings:

- Give each receiver its own channel×edge sensitivity: detection **0.65645 → 0.47579**, ratio MSE **0.32182 → 0.17606**. The result is not explained by omitting these receiver-specific lane effects.
- Shuffle direction trajectories **within scan, receiver, channel, edge and sample rate**, using 100 fixed seeds and the original fitted coefficients. Median M1 detection loss is **0.78309** (central 95% of these shuffled losses: 0.70500–0.83641); median ratio MSE is **0.36423** (0.31292–0.40998). Actual directions outperform these more restricted controls. These are descriptive controls, not significance probabilities.

## Association quality and uncertainty

Among 242 reciprocal scored candidate pairs, 92.6% independently choose the same MAP satellite. This is consistency evidence, not decoded identity. The median MAP training RMS is 156.2 Hz, with 10th/90th percentiles 57.0/473.5 Hz. About 93.8% of tracks put more than 0.95 of the truncated weight on one candidate; given the fixed 100 Hz scale and correlated observations, this must not be interpreted as 95% calibrated association confidence.

Descriptive 2,000-resample, whole-scan bootstrap intervals for M1−M0 are −0.235 to −0.105 detection loss and −0.200 to −0.085 ratio MSE. There are only four chronologically adjacent test scans. These are **not formal population-confidence intervals or evidence of broad temporal generalization**; all resamples improving largely follows from all four observed scans improving.

## Interpretation and next step

There is useful directional reception information in this roof subset beyond the tested sensitivity nuisances. It justifies the next experiment: combine a calibrated reception likelihood with Doppler/TLE uncertainty and evaluate **independently generated** Sacramento- and Reno-prior candidates on unseen scans. Do not share truth-derived candidates, and do not make reception a hard satellite-rejection rule.

This run does **not** evaluate a calibrated physical beam model, independent unknown-position search, or geographic-error reduction. The known position was used to generate directions on both calibration and test scans. Two strong receivers indicate overlapping response, not uniquely zenith; the nominal symmetric tilts primarily offer an east/west constraint. Matched-template measurements on both receivers, including the weaker receiver below its discovery gate, remain the appropriate next power-calibration experiment.

## Artifacts and reproduction

- `PROTOCOL.md`, `manifest.json`, `inventory.json`: original design/freshness panel.
- `evaluation_manifest.json`, `evaluation_inventory.json`: frozen readiness-selected cohort and verified sources.
- `associations.json`, `source_links.json`: direction hypotheses and exact source links.
- `pairing_summary.json`, `model_rows.json`, `results.json`: complete primary evaluation and checksums.
- `stricter_controls.json`: explicitly post-result robustness controls.

Use the installed acquisition runtime, which supplies the public tracking-input APIs; this checkout's development environment does not necessarily include those deployed APIs. The caches are local, digest-verified analysis objects, not public persisted contracts.

```bash
sudo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_roof_direction_subset/evaluate.py
sudo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_roof_direction_subset/stricter_controls.py
sudo /opt/leo-tracker/current-api/.venv/bin/python -m pytest -q reports/2026_09_27_roof_direction_subset
```

Do not rerun the selection step or silently refresh readiness to reproduce this cohort. No production contracts or golden scientific fixtures were changed.
