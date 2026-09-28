# SOL evaluation: roof dual-receiver geometry

## Result

The existing roof corpus supports a **dual-receiver reception feasibility result**, but not a directional or geographic result. In the only analysis-complete holdout (`scan-fw-c78fb2dba2465361`), 1,024/2,216 visits had candidates compatible across receivers under the frozen epoch/CFO rule; none remained compatible under the fixed channel-and-edge-preserving long-time shift. This establishes that simultaneous products contain shared signal structure. It does not establish satellite identity, antenna gain, or arrival direction.

The M1 directional, M2 beam, and position stages were **not yet evaluated**. Candidate compatibility remains a proxy, only one holdout was analysis-ready, and the reception outcome cannot be used to select the candidate direction it is meant to predict.

## Frozen inventory and readiness

All eight pose companions passed canonical binding-digest verification. Each companion source-manifest digest matched installed read-only `AdaptiveHopIqStore.inspect()`. Complete analyses were loaded through the public tracking-input port, which constructs its analysis binding from that capture manifest. Capture order came from capture UTC bounds, not filenames or publication times.

| Split | Session | Complete visits | Published analysis visits | Status |
|---|---|---:|---:|---|
| calibration | `2e6b…` | 2,222 | 2,222 | ready, pre-repair |
| calibration | `322179…` | 2,214 | — | incomplete, excluded from fits |
| calibration | `195bdb…` | 2,215 | 2,215 | ready, repair state uncertain |
| calibration | `60d9d1…` | 2,218 | 2,218 | ready, verified post-repair |
| calibration | `cd6a02…` | 2,214 | 2,214 | ready, verified post-repair |
| holdout | `c78fb2…` | 2,216 | 2,216 | ready |
| holdout | `c7e37f…` | 2,211 | — | metrics manifest incomplete; excluded |
| holdout | `5eaaa2…` | 2,218 | — | metrics manifest incomplete; excluded |

The two pending holdouts and the incomplete `322179…` calibration were excluded before any fit or score and were not replaced. Readiness is established through public `ScannerTrackingInputStore.load()`, which requires the authoritative complete metrics manifest and full visit coverage; partial files never enter the evaluator. The postrepair sensitivity uses only the two verified postrepair calibration scans. Of the other ready calibration data, only the 23:30 scan has a confirmed RX0 floor failure; the 23:50 repair state is uncertain.

## Pairing and opportunity result

A candidate is compatible only when receiver epochs agree modulo the 750 Hz frame period within 2.2 µs and alias-aware CFO difference is within 10 kHz of the calibration modal receiver bias (3,921.7 Hz). The epoch tolerance is symbol-duration motivated; the CFO window is a heuristic from the existing estimator primitive. Neither has an empirically measured match-error rate. Near-identical optimizer candidates can duplicate the same mode, so multiplicity is not interpreted as independent ambiguity and the output is labelled compatibility, not identity.

Complete-holdout opportunity accounting:

| Category | Visits |
|---|---:|
| both detected, compatible candidate | 1,024 |
| both detected, no compatible candidate | 298 |
| RX0 only | 437 |
| RX1 only | 75 |
| neither | 382 |

The fixed channel-and-edge-preserving half-series shift (minimum 100 positions) yielded zero compatible visits, 1,119 both-detected/unmatched, 640 RX0-only, 278 RX1-only, and 179 neither. These altered single-receiver categories arise because the control deliberately combines different observation times. It is a compatibility diagnostic, not a false-match calibration. Receiver swapping with the CFO-bias sign reversed preserved 1,024 compatible visits and exchanged the RX-only counts, as required by symmetry.

GLRT fractional margin was used only for the published 0.025 detection gate and compatibility candidates. It is a detection proxy, not calibrated power, SNR, or antenna gain. No phase-center or gain claim is made.

## Receiver/channel baseline and hardware confound

The 23:30 calibration has the documented broadband RX0-floor failure. The 23:40 scan is analysis-incomplete and excluded; the 23:50 repair state is uncertain. The four-ready-scan receiver/channel intercept baseline scores 0.7505 mean Bernoulli log loss on the complete holdout; the predeclared postrepair-only sensitivity scores 0.5980 over 4,432 receiver observations. This improvement is evidence of hardware-regime sensitivity, not directional information. Two verified postrepair calibration scans are insufficient for a broad beam claim.

For nominal symmetric ±10° boresight vectors, their **dot-product difference** with arrival unit vector `u` is `2 sin(10°) u_E`. This is boresight geometry, not an arbitrary antenna-gain response. It supplies only one east/west contrast, with an entire north/south symmetry plane. Moreover the connector mapping, world elevation/tilt, RF phase centers, beamwidth, and gain response are unknown. The operator-supplied WGS84 position is therefore not described as surveyed GPS, and east/west labels are not calibrated antenna axes.

## Conclusion

The receivers often observe compatible simultaneous pilot hypotheses after repair, and compatibility collapses under the fixed long-time shift. That is enough to justify later paired-signal work. It is not enough to show that relative reception improves satellite discrimination or position beyond receiver/channel sensitivity. M1, M2, and location consequences remain unevaluated. The next bounded existing-data test is to derive direction hypotheses from Doppler-only training candidate posteriors, cross-fit signed RX margin contrast without using reception to choose identity, and compare M0/M1 on all three frozen holdouts once their authoritative bundles publish, including receiver-mapping reversal. No geographic accuracy claim is supported, and no truth-guided candidate sharing or location search was performed.

Reproduce after the two pending analysis bundles become complete:

```bash
sudo /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_27_roof_geometry_evaluation/verified_run.py
sudo /opt/leo-tracker/current-api/.venv/bin/python -m pytest -q reports/2026_09_27_roof_geometry_evaluation/test_verified_run.py
```

`verified_results.json` is the corrected public-port result. `run.py`, `test_run.py`, and `results.json` are superseded drafts retained for audit history, not the reproduction path. Preserve a copy of the corrected result before rerunning as publication readiness can change.
