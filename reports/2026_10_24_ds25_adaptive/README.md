# DS25: adaptive-only 10 MS/s scans and the same-interval fast comparison

DS25 contains **69 complete adaptive scans at 10 MS/s**, selected from DS24 revision 2. Its acquisition-start interval is **[2026-10-21 23:42:37 UTC, 2026-10-24 14:38:14 UTC)**, ending October 24, 2026 at 7:38:14 a.m. PDT. The comparison cohort contains the **34 fast 10 MS/s scans** in that same frozen interval. Fast scans are comparison cases, not members of DS25.

Membership has no GLRT-readiness, signal-quality, position-error or satellite gate. Each DS25 label maps to its original DS24 label in the manifest. DS24 remains unchanged. Previously excluded 2.5 MS/s recordings remain outside this 10 MS/s study.

The numerical results, completion counts and figures are in [RESULTS.md](RESULTS.md). The distribution denominator is the number of localized scans; missing or failed scans are accounted for separately against all 69 adaptive and 34 fast acquisitions. Missing inputs are not assigned zero position error.

## Main result

The current baseline localized **68/69 adaptive scans and 24/34 fast scans**. With fitted c, adaptive mean/median/p95 error is **1.595 / 1.241 / 3.992 km**, compared with **1.220 / 1.114 / 2.131 km** for fast scans. With c=0, the corresponding means are **1.587 and 1.202 km**. Fast scans have lower observed mean and tail error in both controls.

The within-1-km rates among localized scans are similar: **28/68 adaptive (41.2%)** and **10/24 fast (41.7%)** with fitted c. The larger adaptive errors are the main practical difference: its worst result is **DS25-0061 at 8.145 km**, versus **DS24-0089 at 2.205 km** for fast. This study identifies those outliers but does not diagnose their association or orbit-model errors.

Restricting the comparison to eight shared 3-hour blocks and giving each block equal weight yields fitted-c means of **1.710 km adaptive and 1.229 km fast**. The adaptive-minus-fast difference is **+0.481 km**, with a block-bootstrap 95% interval of **−0.243 to +1.320 km**. The direction remains the same, but the interval includes zero; this limited observational cohort does not establish a precise or universal mode advantage.

The original ALGO02 control gives fitted-c means of **1.724 km adaptive and 1.240 km fast**. The current baseline improves those observed means to **1.595 and 1.220 km** on identical per-mode localized cohorts. Fitting c slightly reduces mean frequency RMS while slightly increasing mean geographic error for both modes, reinforcing the need to report these metrics separately.

All 103 cases reached terminal accounting in approximately **25 minutes**, using eight process-isolated workers. There were no execution failures or timeouts. Ten fast members lacked frozen GLRT inputs. DS25-0037 exported successfully but supplied only 70 GLRT points and four graph tracks, none with qualifying active curvature; it remains unlocalized. Seven owned tests pass, and the final audit verifies **1,589 prepared-file hashes and 1,020,577 historical element versions** across the cohort.

## Algorithm and controlled comparison

The primary method is the fresh baseline used in the preceding DS24 study: **ALGO02, qualified causal signed phase prior, then satellite-family comparison with equal assignment priors**. Original ALGO02-v1 is retained as a secondary control. This is the same fresh-scan pipeline for adaptive and fast recordings. It does not reuse the experimental DS23-specific graph-reentry candidate banks or claim equivalence to every experimental ALGO-series extension.

Each scan independently starts at the center of a **25 × 25 km** region, **37.906°, −122.545°**. Existing GLRT products feed the same graph-track construction, causal satellite-catalogue search and position fitting. Adaptive inputs are exported through the published `ScannerTrackingInputStore` using the existing 120 ms probe stride. Fast inputs use their frozen published tracking contracts. The two acquisition formats produce different observation sets and channel coverage; comparison of their resulting errors is observational, not a controlled causal test of acquisition mode alone.

All 69 adaptive acquisitions are configured for **channels 1–4**, whereas all 34 fast acquisitions cover **channels 1–8**. Adaptive recordings retain 87–2,205 visits each; fast recordings contain 6,768–6,774 windows each. These counts describe the existing acquisition policies and are not used to filter the comparison. A poor-evidence scan remains in the denominator even when no curved track qualifies for localization.

Every scan runs both **c=0 and fitted-c** with matched observations, candidate identities, aliases, other priors and search budgets. Geographic accuracy is reported separately from curved-track frequency RMS. Lower in-sample frequency residuals alone do not establish a more accurate position.

Only TLE elements and causal history available before each scan are permitted. There is no cross-scan stationary-position pooling, GPS-driven association choice or post-observation TLE substitution. A fixed RF-based policy chooses the shared hypothesis for both c arms. Geographic evaluation is deferred until terminal accounting for the entire cohort.

The evaluation reference is **37.849061591561885°, −122.48574968092912°**, the previously supplied site coordinate. It enters only the reporting script. These data assess later recordings at that site, not generalization to a different location.

## Time coverage and missing data

Sharing an interval does not mean that fast and adaptive acquisitions are simultaneous. The report includes error versus acquisition time, and a sensitivity analysis restricted to **3-hour UTC blocks containing localized scans of both modes**. Each shared block receives equal weight. The adaptive-minus-fast mean difference is bootstrapped by resampling whole shared blocks, using 4,000 deterministic resamples. This reduces sensitivity to unequal temporal coverage but does not eliminate selection bias from missing inputs or dependence between nearby scans.

Existing upstream GLRT products are used without an IQ reprocessing campaign. Failed export, preparation, inference and time-cap outcomes remain in the case table. A successful internal RF-policy fallback is a valid final position, rather than an omitted case. The primary family-comparison method is reported only when its stage completes; original ALGO02 results remain separately available if that later stage fails.

Fast input availability is the frozen tracking-contract inventory carried by DS24 revision 2. Adaptive products are exported through the public port as each case starts; each export is then hash-frozen before fitting. These readiness snapshots are not simultaneous. Reported missing inputs refer to this study's sealed inputs, not a claim that no later processing product can exist.

The process-isolated supervisor runs eight jobs with one numerical-library thread each. Stage limits are 180 seconds for export, 600 seconds for preparation, 900 seconds for ALGO02, and 960 seconds for family comparison. The same limits apply to both acquisition modes. No extra search budget is allocated based on geographic error.

## Dataset authorities and reproducibility

The complete DS25 authority is [dataset/manifest.json.gz](dataset/manifest.json.gz). This is lossless gzip; [dataset/manifest.sha256](dataset/manifest.sha256) hashes its **decompressed bytes**. The full local JSON is `/srv/bulk/leo/research/ds25-20261024/dataset/manifest.json`. Per-chunk IQ hashes and in-place storage references are retained from the verified parent. IQ is neither copied nor fully rehashed for this subset mint.

[sample.json](sample.json) freezes the combined analysis cohort and explicitly identifies each scan's mode. It is an analysis input, not DS25 membership authority. [protocol.json](protocol.json) freezes the methods and budgets; [source_receipt.json](source_receipt.json) pins the local numerical sources. [dataset/verification.json](dataset/verification.json) checks the adaptive-only subset, disjoint fast comparison cohort, identical interval and 10 MS/s metadata. [audit.json](audit.json) checks prepared-file hashes, causal element timestamps, history timestamps, paired RF gates and matched point counts without loading geographic truth.

The local run directory is `/srv/bulk/leo/research/ds25-20261024`. Full prepared inputs and numerical trial products remain there; publication contains their hashes and compact final records. The research sources require the existing repository numerical environment and read-only corpus access. They are not a standalone IQ distribution.

`mint.py` creates the dataset and analysis cohort and refuses to overwrite an existing frozen sample. `engine/run_all.py` runs the matched inference pipeline. After every case reaches terminal accounting, run `audit.py`, then `report.py`. Use the repository `.venv/bin/python -B`, `PYTHONDONTWRITEBYTECODE=1`, one BLAS thread and `PYTHONPATH=/tmp/algo03-feasible-deps:/srv/bulk/leo/research/ds25-20261024/engine:src:tools`.

Owned tests cover dataset selection and parent labels, unchanged-input handling, empty-predictive compatibility, refusal of unqualified references, geographic-distance arithmetic, missing-case denominators, and shared-time-block weighting. None changes golden scientific fixtures or production inference components.
