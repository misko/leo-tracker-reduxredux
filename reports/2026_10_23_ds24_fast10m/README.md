# DS24: fresh 10 MS/s fast recordings and native-evidence position comparison

DS24 contains **all 19 discovered, complete 10 MS/s fast recordings** whose acquisition starts fall within the frozen 48-hour window, 2026-10-21 23:42:37 UTC through 2026-10-23 23:42:37 UTC. **The numerical comparison is incomplete for the full dataset:** only eight recordings had published tracking-input contracts at the membership freeze. Eleven missing-input recordings remain in the manifest, result tables and failure denominator. The completed numerical subset and its position-error distributions are given in [RESULTS.md](RESULTS.md).

No new ALGO version is promoted. The proposed policies were applied without tuning against DS24 GPS errors. This is a new-recording comparison at the same evaluation site, not validation at a new geographic location.

The native-evidence proposals come from the preceding [DS23 opportunity review](../2026_10_23_ds23_opportunity_review/README.md).

## Completed subset result

All eight analysis-ready recordings completed all six final policy comparisons in both c arms. All 19 members have terminal accounting: eight completed comparisons and eleven missing upstream inputs. No analysis hit a time cap. One adapter failure on 0019 occurred before native discovery or fitting; the preserved failure was corrected by normalizing an absent empty-evidence field, and the remaining stage completed with identical baseline coordinates. No scientific fit was restarted to obtain a different answer.

On these eight scans, the existing native policy changes mean position error from **1.224 to 1.155 km with c=0** and **1.244 to 1.224 km with fitted c**. It increases pooled association from **76.57% to 79.31%**. This is a modest mean gain relative to the current family-cavity baseline, not a demonstrated full-DS24 improvement. Unmodified ALGO02 has fitted-c mean 1.223 km, essentially the same as the existing native policy on this subset.

The temporal-contrast proposal has fitted-c mean **1.250 km**, median **1.050 km**, and p95 **2.098 km**, versus baseline **1.244 / 1.120 / 2.025 km**. Its median improves, but its mean and tail do not. It falls back on three scans. This does not support promoting it as a generally better position policy.

The fixed-position proposal accepts **1,177 additional physical GLRT points**, raising association to **79.44%**, with exactly unchanged baseline positions on all eight scans. It has no scientific fallback. This demonstrates an association-coverage improvement independent of position improvement; it does not resolve the remaining position bias. The current full native policy, matched-start full control and contrasts have 1, 2 and 3 baseline fallbacks respectively. The full native policy uses the original constrained rescue on 0015; its especially favorable c=0 movement should not be attributed to the contrast objective.

## Membership and input readiness

There are 128,673 recorded windows and 156,145,087,752 compressed bytes referenced in place. All 19 recordings are complete; raw metadata/index/payload-size checks found zero integrity errors. Raw IQ payloads were not copied or fully rehashed. Inventory deduplicated migrated storage copies and used actual 10,000,000-sample/s recording metadata. Another 56 in-window fast recordings were verified as 2.5 MS/s and excluded by the requested rate criterion.

The [hardware UTC audit](acquisition_start_audit.json) independently checks acquisition start against the first sample-counter UTC bracket. Earliest capture is 2026-10-23 04:42:32 UTC; no member is near the cutoff. Manifest creation differs from those acquisition brackets by at most about 22 ms.

At the frozen readiness snapshot:

| Recordings | Count | Existing input state |
|---|---:|---|
| DS24-0001–0009 | 9 | Earlier GLRT processing failed; no published tracking contract |
| DS24-0010–0011 | 2 | Already queued/running in existing native backfill |
| DS24-0012–0019 | 8 | Complete, hash-pinned tracking inputs available |

The [readiness audit](readiness_audit.json) checked published report content, not just expected filenames. No complete alternate contracts were found for the eleven missing members. Their absence is not a failed localization result or evidence of poor RF signal quality.

Measured existing native processing takes roughly 14–17 minutes per recording at 20 workers. Rebuilding the nine failed inputs would require roughly 2–2.6 hours at that concurrency; the existing backfill already occupies those workers. This bounded iteration did not launch another multi-hour GLRT campaign or interfere with it. The full-DS24 position distribution remains unavailable until those inputs are rebuilt and analyzed. The ready subset is not a random sample of the 19 recordings, so its accuracy statistics must not be described as full-DS24 performance.

## Algorithms and controls

Every numerical scan starts from the original 25 × 25 km region centered at **37.906°, −122.545°**, with fresh graph tracking, causal TLE inputs and a cold ALGO02 discovery. No DS23 numerical results, frozen reentry candidate banks, or preselected satellite identities are used as fresh-scan inputs.

| Result name | Meaning |
|---|---|
| `algo02_historical` | Fresh execution of the published ALGO02-v1 control |
| `baseline` | Fresh ALGO02, existing qualified causal signed phase prior, then the published equal-assignment-prior family-cavity policy |
| `native_full` | Baseline plus existing persistent-path recovery, original cold native fit and existing near-feasible rescue policy |
| `native_full_matched` | Same native observations, using the same parent start and scalar solver budget as the contrast variant |
| `native_fixed` | Qualify recovered native paths while holding the baseline position fixed |
| `native_contrasts` | Fit baseline curved evidence plus the joint within-path temporal-contrast likelihood, removing predictive-path constant frequency levels |

The primary baseline is the ALGO02/ALGO03-derived family-cavity reference, rather than unmodified ALGO02 alone. The later experimental ordinary graph-reentry study depended on DS23-specific hypothesis banks; that additional experimental reentry layer is **not** silently reused or claimed here. Native recovery operates on the freshly reconstructed reference. Thus this experiment tests the proposed native-evidence changes on fresh scans; it is not a parity rerun of every stage of the rejected DS23 ALGO04 candidate.

Both c=0 and fitted-c arms use the same observations, aliases, candidate hypotheses, other priors and search budgets. Candidate decisions use the existing c0 ranking and paired qualification; GPS does not select a method, family, path, prior or endpoint. The causal catalogue and phase history precede each scan. There is no cross-scan stationary position pooling.

The native alternatives share the same persistent-path proposals and aliases. Whole paths pass the existing fixed-parent screening; no residual point trimming is introduced. Each alternative must pass the original residual/visibility/phase gates in both arms and preserve all baseline accepted physical IDs. A rejected candidate falls back to the qualified baseline. Such a fallback remains a valid final position in the distribution and is separately counted; an execution failure is reported separately.

`native_full_matched` and `native_contrasts` each use five phase refreshes with up to 48 scalar SLSQP iterations per refresh, starting at the same baseline endpoint. The existing cold-fit/rescue control remains separate so an optimizer-start change cannot be mistaken for an effect of removing frequency levels. These are bounded research solvers, not an embedded runtime benchmark.

## Exact temporal-contrast likelihood

For predictive residual y with shared covariance K, form an orthonormal set of within-path temporal contrasts C. The alternative uses the Gaussian density of C y with covariance C K Cᵀ. Constants are removed independently per predictive path; slopes remain. This affects all predictive entries, including parent linear entries, not solely the newly discovered points. The original curved likelihood and its nuisance priors remain present, and native points do not enter the radio-calibration normal equations.

The implementation uses a restricted-likelihood identity and Woodbury solves to avoid repeatedly constructing a large dense contrast covariance. For normalized group-indicator columns X, the quadratic is `yᵀK⁻¹y − bᵀ(XᵀK⁻¹X)⁻¹b`, where `b=XᵀK⁻¹y`. The log determinant is `log|K| + log|XᵀK⁻¹X|`; normalization uses the remaining contrast dimension. Shared receiver/orbit uncertainty is retained. Group-constant uncertainty cancels algebraically.

Two numerical tests check correlated dense replay, invariance to path constants and constant uncertainty, and an empty contrast space. A real-scan audit checks 453 predictive points on 25 paths, giving 428 contrast dimensions: direct dense and structured scores agree within 4×10⁻¹² in both c arms. Native predictive evidence changes the curved calibration coefficients by exactly zero. See [first_native_covariance_audit.json](first_native_covariance_audit.json).

Dropping constants deliberately discards some frequency information. The earlier two-endpoint diagnostic motivated this test; it did not establish that the new objective would locate the receiver better. Absolute scores from full and contrast likelihoods have different observation dimensions and must not be compared to select a better model. Position accuracy, gate behavior, coverage and frequency-fit diagnostics are reported separately.

## Evaluation and figures

The user confirmed that every recording was taken at **37.849061591561885°, −122.48574968092912°**. That coordinate is stored separately in [evaluation_reference.json](evaluation_reference.json) and used only by the reporter to calculate great-circle error.

The figures compare the same qualified recording intersection across all six policies in each c arm. Both the box plots with individual observations and empirical cumulative distributions are linked from [RESULTS.md](RESULTS.md). The underlying [per-recording CSV](tables/positions.csv) includes all 19 members for every method and arm, including missing inputs. [summary.json](summary.json) retains completion denominators, pooled GLRT association counts and policy fallback counts.

Reported RMS is the existing curved calibration residual diagnostic. It is not pooled RMS over all newly recovered native points. A lower RMS or higher association percentage alone is not evidence of better position accuracy. The small, readiness-selected cohort cannot establish full-dataset or new-location improvement. No best-per-scan GPS selection is used to combine algorithms.

An association count means unique original GLRT points accepted by the current model and its gates. It is not an independently verified satellite-identity or signal-purity measurement.

## Reproduction and audit

Membership is immutable in [manifest.json](manifest.json), [sample.json](sample.json) and [seal.json](seal.json). [study_protocol.json](study_protocol.json) freezes inference methods, input hashes, settings and source closure. Subsequent source receipts document supervisor-only fixes for process-group timeouts and truthful failure accounting; the original freeze remains preserved. No golden scientific fixtures or production inference components were changed.

Research drivers and component tests are in [engine/](engine/), [contrast/](contrast/) and [reporting/](reporting/). Numerical case artifacts remain at `/srv/bulk/leo/research/ds24-20261023`; their provenance is retained separately from publication. This capsule requires that existing numerical environment and read-only corpus access, not a standalone distribution of raw recordings.

Use the repository `.venv/bin/python -B`, `PYTHONDONTWRITEBYTECODE=1`, one BLAS thread, and `PYTHONPATH=/tmp/algo03-feasible-deps:/srv/bulk/leo/research/ds24-20261023/engine:src:tools`. `engine/run.py --stage baseline` supervises fresh preparation and inference; `engine/pipeline.py` waits for individual baseline receipts and launches the native variants. Preserve completed results rather than rerunning scans to obtain a different answer.

Run `reporting/report.py` in the numerical environment to regenerate tables and figures. `reporting/audit.py` independently verifies physical-ID ownership, denominators, baseline-ID preservation and identical fixed-policy coordinates. Reporting is the only stage receiving the evaluation coordinate. The first-scan read audit confirms the exercised fresh adapter/context/objective paths did not load historical scientific report products; this bounded trace is not a blanket audit of every possible import or future code path.

The independent [prepared-input audit](prepared_input_audit.json) verifies all 19 preparation receipts and all eight usable banks: 12,766 selected candidate-element records and 94,340 historical versions, plus previous TLE and validation-target timestamps, satisfy the per-scan pre-observation cutoff. The [output audit](output_audit.json) passes all eight comparisons, including accepted gates, unique original physical IDs, denominator arithmetic, baseline-ID preservation and fixed-position equality.

Ten engine/contrast/reporting unit tests pass; the compact publication exporter has one additional owned test. Separate live timeout checks pass for ordinary and elevated read-only subprocesses. The real covariance replay and all-input/output audits supplement those tests. Both final figures were visually inspected. The source amendments are orchestration or empty-evidence-summary compatibility fixes; numerical objectives and budgets remain those of the frozen study.
