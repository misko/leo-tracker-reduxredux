# Shared-residual validation on the frozen 20-visit track replay

The shared-residual diagnostic was developed on visits 1354 and 1428, the two largest historical contiguous-symbol-half disagreements in the frozen 20-visit scan-hop-6ad replay. It was then replayed without modification on the other 18 visits from `scan-hop-6adcb067e2dbce43-raw-phase20-v1.json`. Every visit bound to the same persisted RX0/RX1 track pair by alias-aware frequency evidence; phase was not used for selection. All 20 visits evaluated and no failure was dropped.

All phases below are transported to each visit's historical full-window center. This avoids comparing phases at slightly different weighted fit centers.

| Cohort | Visits | Historical half disagreement, min / median / max | Shared half disagreement, min / median / max | Shared-vs-historical full phase shift, min / median / max |
|---|---:|---:|---:|---:|
| Development | 2 | 113.18° / 118.13° / 123.08° | 4.67° / 12.39° / 20.11° | 7.01° / 11.99° / 16.96° |
| Validation | 18 | 2.00° / 11.91° / 72.90° | 0.03° / 3.17° / 54.84° | 0.44° / 2.23° / 12.79° |

The shared-residual half disagreement was smaller in all 18 validation visits. The validation median fell from 11.91° to 3.17°, while the 54.84° maximum shows that a common residual does not remove every within-dwell inconsistency. The common-time full-window phase also changed by as much as 12.79° on validation. The method therefore exposes and reduces one receiver-specific phase-reference ambiguity, but it does not establish a uniquely correct absolute phase observable.

Both ±227272.73 Hz wrong-symbol authorities were retained for every visit. Across the 40 controls, resultants span 0.490–0.979 with median 0.768; nine exceed 0.9. Exact-to-control floors span 0.616–37.07 with median 3.24; 27 exceed 2. These controls confirm that ordinary pilot coherence and control rejection cannot validate the externally supplied symbol branch.

The replay used saved IQ only and did not collect RF. The complete per-visit rows, including pair binding, fit centers, wrong-alias controls, and any failure state, are in `reports/figures/2026_09_21_phase_half_audit/scan-hop-6adcb067e2dbce43-shared-residual-phase20-v1.json`. Its canonical evidence digest is `sha256:8c8f3974e3b4d2018c59677ce633ce35943971ff3431118a33f5da58bdfd6906`.

Reproduce the result with:

```bash
sudo -u leo env PYTHONPATH=src .venv/bin/python \
  tools/report_adaptive_dual_rx_shared_residual_audit.py \
  --bulk-root /srv/bulk/leo \
  --session-id scan-hop-6adcb067e2dbce43 \
  --visits 1354,1394,1428,1444,1461,1478,1498,1514,1528,1542,1559,1574,1588,1602,1618,1633,1650,1667,1690,1713 \
  --json /tmp/shared-residual-phase20.json
```
