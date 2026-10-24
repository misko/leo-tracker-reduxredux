# DS24 fast scans: independent CH1–4 and CH5–8 localization

**Reporting correction (2026-10-24):** The original association-count summary omitted some predictive likelihood points stored as `additional_predictive_points`. The corrected unique position-likelihood totals are **78,067/108,600 (71.88%)** for CH1–8, **42,621/60,059 (70.97%)** for CH1–4, and **33,339/48,541 (68.68%)** for CH5–8 in both c arms. All fitted positions and geographic-error statistics are unchanged. The original [positions CSV](tables/positions.csv), [summary JSON](summary.json), and compressed raw fits remain unchanged as legacy reporting artifacts; use the [new per-scan count audit](../2026_10_24_ds24_bottlenecks/evidence/likelihood_count_audit.csv) and [bottleneck investigation](../2026_10_24_ds24_bottlenecks/README.md) for corrected counts and interpretation.

This study reruns **all 34 fast 10 MS/s members of DS24 revision 2** with **CH1–4 only** and **CH5–8 only**, and compares them with the existing CH1–8 results from the same recordings. It preserves the DS24 interval, **[2026-10-21 23:42:37 UTC, 2026-10-24 14:38:14 UTC)**, ending October 24 at 7:38:14 a.m. PDT. Adaptive scans are outside this study.

The final tables, per-scan plots, error distributions and missing-run accounting are in [RESULTS.md](RESULTS.md). No new ALGO version is promoted by this ablation.

## Findings

All three channel selections localize the **same 24 scans**. The other ten lack the same frozen upstream inputs in every group. All 48 usable channel-restricted fits completed in approximately **13 minutes**, with no execution failures, timeouts or rejected final paired fits.

| Channels | Mean error, c=0 | Mean error, fitted c | Median, fitted c | P95, fitted c | Worst, fitted c |
|---|---:|---:|---:|---:|---:|
| CH1–8 | 1.202 km | 1.220 km | 1.114 km | 2.131 km | 2.205 km |
| CH1–4 only | 1.538 km | 1.558 km | 1.512 km | 2.509 km | 3.687 km |
| CH5–8 only | 2.040 km | 2.040 km | 2.001 km | 4.070 km | 6.190 km |

**Keeping all eight channels gives the best observed mean and tail accuracy.** Restricting to CH1–4 raises fitted-c mean error by **0.337 km**, improving nine scans and worsening fifteen. Restricting to CH5–8 raises it by **0.820 km**, improving seven and worsening seventeen. The mean-error ranking is identical with c=0. These are fixed-policy results, not an oracle that chooses the best channel subset using GPS.

CH1–4 provides **60,059 GLRT points**, whereas CH5–8 provides **48,541**, compared with **108,600** using all channels. The corrected accepted position-likelihood percentages are **70.97%, 68.68%, and 71.88%**, respectively, counting the unique union of accepted curved and explicit predictive IDs. CH1–4's mean curved residual RMS is lower than the full-channel result (**67.02 vs 71.38 Hz**, fitted c), even though its position error is higher. This directly illustrates why a lower in-sample CFO residual is insufficient evidence of better localization.

The strongest CH5–8 outliers are **DS24-0015 at 6.190 km** and **DS24-0097 at 4.228 km**. CH1–4's worst result is **DS24-0089 at 3.687 km**. These are useful targets for a follow-up ambiguity/geometry investigation; this channel ablation alone does not determine whether each error comes from satellite identity, nuisance freedom or weak geometry.

The original ALGO02 secondary control has fitted-c mean errors of **1.240 / 1.526 / 2.432 km** for CH1–8 / CH1–4 / CH5–8. Thus the current signed-prior/family-comparison extension helps the high-channel half on average, but slightly worsens the low-channel half. The method comparison is retained in the report rather than choosing the better algorithm separately for each subset after seeing GPS errors.

Relative to the prior DS25 study, CH1–4-only fast mean error (**1.558 km**) is close to adaptive mean error (**1.595 km**), while full-channel fast mean error was **1.220 km**. This is consistent with extra channels contributing to the earlier fast-scan advantage. It is not a clean acquisition-mode attribution: the adaptive cohort contains different recordings and times, and the acquisition schedules and available RF evidence still differ.

Three owned tests pass. The independent audit verifies exact partition of the original observations on all 24 usable scans, noise and track channel isolation, **856 prepared-file hashes**, and **515,783 historical element versions**. The reused all-channel numerical results match all **48 published final-result hashes** from the preceding study.

## What is rerun

For each half, the adapter selects channel-specific physical GLRT winners **before** graph construction, radio-noise estimation, calibration, satellite association or position fitting. It retains the original timestamps, CFOs, receiver identifiers, RF frequencies, sample clocks and physical observation IDs. It does not shift the time origin to the first retained point.

The original hash-pinned tracking contract is retained intact as source authority. The channel selection is applied in the preparation adapter rather than rewriting that persisted public contract. A separate audit verifies that the two observation subsets are disjoint, together equal the original winning observations, and contain exactly the original records without changing any field. Tracks and numerical likelihood inputs contain only the allowed half's points. Excluded channels do not calibrate the receiver or contribute constraints to the fit.

Each half constructs its own graph tracks and independently searches the broad causal satellite catalogue from the regional starting point. It does not inherit the full-channel satellite assignments, fitted position, receiver calibration, learned noise or selected tracks. Removing channels may change retained tracks, associations and the amount of evidence supporting the position; those changes are part of this end-to-end ablation.

The primary algorithm is the same fresh baseline used for the preceding DS24/DS25 comparison: **ALGO02, qualified causal signed phase prior, then equal-assignment-prior satellite-family comparison**. Original ALGO02-v1 is a secondary control. The later experimental DS23-specific graph-reentry candidate banks are not used.

Every fit starts at `(0,0)` in the **25 × 25 km** region centered at **37.906°, −122.545°**. Only elements and orbit history available before that recording are permitted. There is no GPS-based satellite selection, post-scan TLE substitution or stationary position pooling. The known evaluation coordinate, **37.849061591561885°, −122.48574968092912°**, is used only by the reporter after all runs and audits finish.

Both **c=0 and fitted-c** are run for every half, matching observations, candidate identities, aliases, other priors and search budgets between c arms. The channel subsets deliberately have different observations. RF residual RMS and association fractions are reported separately from geographic error.

## Matched inputs and comparison population

The fast source contracts and their availability are frozen to the preceding DS24/DS25 comparison. **24 of 34 scans have usable contracts; ten lack them** in that snapshot. No GLRT rebuild is launched, and newly completed upstream products are not silently substituted for missing inputs. This ensures that the two subsets and all-channel reference share the same underlying measurements and missing-input denominator.

The CH1–8 reference reuses the completed prior results; both channel-restricted runs are fresh. The audit pins the reused result files and verifies identical original tracking hashes. Results for all 34 members remain in the CSV even when no position is returned.

The primary error table uses the **intersection of successful scans across CH1–8, CH1–4 and CH5–8**, separately for each method. Within a method, success requires a paired c=0/fitted-c result. This prevents different missing-case selections from producing a misleading mean comparison. `summary.json` also preserves all-available per-group statistics and failure counts. Per-scan error changes compare each subset with the full-channel result on the same scan; there is no GPS-driven best-subset policy.

Association fractions use each group's own GLRT denominator, so a larger fraction can still represent fewer physical observations. The corrected counts include accepted curved calibration and explicit predictive position-likelihood IDs, excluding post-fit-only extensions. These are model-accepted associations, not independent identity ground truth. Frequency RMS describes retained curved calibration evidence; comparing RMS across channel groups is not a matched-observation likelihood comparison.

## Execution and reproducibility

Eight process-isolated jobs run in parallel, with one BLAS thread per process. The per-stage caps match the reference: export 180 seconds, preparation 600 seconds, ALGO02 900 seconds, family comparison 960 seconds. Missing inputs, lack of active curvature, rejected paired fits and time caps remain explicit terminal outcomes.

The study directory is `/srv/bulk/leo/research/ds24-channel-halves-20261024`. [protocol.json](protocol.json) freezes the experiment and inference-source hashes. The channel-specific `sample.json` files preserve all 34 fast members and the parent authority hash; `channels.json` fixes the allowed channels. Dataset membership itself is unchanged.

`filtered_prepare.py` performs the pre-fit channel selection. `run.py` supervises the process-isolated subset runs, using the existing path-explicit numerical engine. `audit.py` checks source hashes, exact physical observation partition, timing preservation, track isolation, prepared-file hashes, causal catalogue/history timestamps, paired residual gates and regional bounds. `base_audit.py` is the unchanged audit from the preceding DS25 study. `report.py` performs geographic evaluation only after terminal accounting and a successful audit.

Full local inputs and numerical trials remain in the study directory. The publication includes hash receipts and compressed final-fit records, per-scan tables, figures and sources. Raw IQ is referenced in place and is not copied or remeasured. The research capsule requires the existing repository environment and corpus access.

Run tests with the repository `.venv/bin/python -B -m pytest -q -p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`. Owned tests verify exact channel partition with unchanged identities and times, explicit empty-subset handling, and intersection-based comparison of successful scans. Golden scientific fixtures and production inference components are unchanged.
