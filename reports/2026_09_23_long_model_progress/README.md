# Long-cohort model experiments: timing helps, short-track removal does not

The frozen blind TRAIN baseline is about 10 km from the reference after six or
sixteen scans and 7.6 km across the full eight-hour group. A conditional fit of
shared per-scan epoch shifts reduces these errors to about 5–6 km in the shorter
views and 1.57 km in the full group at the weakest tested regularization. This is
development progress, but it does not establish sub-300 m accuracy or validation
generalization. Validation/test track outcomes remain closed.

| TRAIN view / model | Sacramento error | Reno error | Common held capped RMS, Sac / Reno |
|---|---:|---:|---:|
| 6 scans, blind zero-epoch baseline | 9.825 km | 9.849 km | 309.26 / 309.27 Hz |
| 6 scans, fixed identities + epoch scale 0.2 s | 9.435 km | 9.439 km | 304.83 / 304.83 Hz |
| 6 scans, fixed identities + epoch scale 1 s | 6.400 km | 6.400 km | 302.69 / 302.69 Hz |
| 6 scans, fixed identities + epoch scale 5 s | 5.091 km | 5.090 km | 302.27 / 302.26 Hz |
| 6 scans, fixed identities + satellite epoch scale 0.2 s | 9.356 km | 9.356 km | 289.82 / 289.82 Hz |
| 6 scans, fixed identities + satellite epoch scale 1 s | 8.035 km | 8.035 km | 207.57 / 207.57 Hz |
| 6 scans, fixed identities + satellite epoch scale 5 s | 4.951 km | 4.951 km | 183.32 / 183.32 Hz |
| 16 scans, blind zero-epoch baseline | 10.039 km | 9.909 km | 334.71 / 335.04 Hz |
| 16 scans, fixed identities + epoch scale 0.2 s | 9.301 km | 9.296 km | 326.78 / 327.40 Hz |
| 16 scans, fixed identities + epoch scale 1 s | 6.678 km | 6.654 km | 322.09 / 322.77 Hz |
| 16 scans, fixed identities + epoch scale 5 s | 5.782 km | 5.754 km | 322.04 / 322.72 Hz |
| 72 scans, full eight-hour group, blind zero-epoch baseline | 7.548 km | 7.651 km | 311.97 / 311.99 Hz |
| 72 scans, fixed identities + scan epoch scale 0.2 s | 6.179 km | 6.181 km | 300.95 / 300.92 Hz |
| 72 scans, fixed identities + scan epoch scale 1 s | 2.236 km | 2.237 km | 294.03 / 293.97 Hz |
| 72 scans, fixed identities + scan epoch scale 5 s | 1.566 km | 1.568 km | 293.91 / 293.85 Hz |
| 72 scans, fixed identities + global epoch scale 0.2 s | 1.887 km | 1.889 km | 302.63 / 302.59 Hz |
| 72 scans, fixed identities + global epoch scale 1 s | 1.698 km | 1.706 km | 302.65 / 302.61 Hz |
| 72 scans, fixed identities + global epoch scale 5 s | 1.690 km | 1.698 km | 302.65 / 302.61 Hz |

Rows labeled simply 'epoch' share one correction per scan; satellite-epoch rows
share one per selected satellite and have no scan term. The satellite model
lowers residuals substantially but still misses by kilometres. All six arms
satisfy the declared objective/step stopping rule, without certified stationarity;
the 5 s arms have three active timing bounds. The accepted solver recomputes the
coupled position/free-epoch step when a bound prevents an outward epoch update.
This corrects a line-search stall in the preserved unprojected attempt.

All settings are reported; no setting was selected by geographic error. These
are nested views of TRAIN, not independent validation. The epoch fit fixes each
identity from the blind baseline and profiles its constant CFO on training rows.
It is therefore conditional inference, not a new full-catalogue association
search. Its fitted shifts may absorb clock, orbit, association or track-model
errors and are not physical clock estimates. The regularization scales are not
calibrated timing uncertainties. For the scan-epoch model, ten of twelve numerical polish runs converged;
eleven arms converged in at least one optimization stage. One scale-5 Sacramento
arm remains line-search limited, with a converged Reno counterpart in the same
basin. No visibility or timing-boundary violations occurred.

![Shared epoch model outcomes](../2026_09_23_long_shared_epoch_position/shared_epoch_results.png)

## What the other experiments tell us

Increasing minimum track span from 3 seconds to 10, 20 or 30 seconds does not
improve the six-scan result. Reference errors remain 9.94–10.59 km, while held
prediction on the fixed all-3s support stays near 309–310 Hz. Scores on the
changing duration subsets are reported separately and must not be compared as
the same population. The fixed-location audit agrees: 3–10 s tracks carry only
1–2% of capped training loss. Their removal is not a supported remedy here.

![Duration ablation with baseline](../2026_09_23_long_training_duration_ablation/reference_error.png)

The full-group fixed-baseline audit also finds distributed residual loss: the
top ten tracks account for only 5.0% and the top ten scans for 28.8% of capped
loss. Only 47–48 of 1,400 selected candidate IDs occur in two scans; none in more
than two. This is descriptive evidence about the selected catalogue assignments,
not verification of true identities or a proof of the error's physical cause.

Fitted epoch terms are much larger than the saved first-sample host brackets,
whose median width is 1.34 ms in this group. The installed PPU source maps FPGA
counters to host time using bracketed register reads; it does not simply stamp
packet receipt. Exact historical package provenance remains unverified. Large
fitted shifts therefore must not be presented as measured capture-clock errors.

The two priors agree on all 476 six-scan identities and 1,124/1,130 sixteen-scan
identities. This is stability between nearby selected solutions, not evidence
that the identities are true. Only one selected ID recurs across two scans in
the first sixteen; none spans three. Consequently persistent satellite effects
have little cross-scan support. Within-scan relative satellite epoch effects
remain a possible regularized model, but require a correct gauge and an actual
Jacobian/geometry-confounding check.

The packed-vector score prototype was equivalent in its checks but 31% slower,
so it is not used. A separate cache-loading fix avoids decompressing the same
NPZ arrays for every track: it produced exactly equal prepared data and reduced
one-scan preparation from 3.171 s to 0.092 s in the recorded benchmark. This is
a loading improvement, not an end-to-end fitting speed claim.

## Synthetic controls and identifiability

The completed direct-SGP4 synthetic control uses the first six TRAIN scans'
476 track supports and 8,285 timestamps with known generating identities. Both
initializations recover a planted noiseless position to numerical precision.
One independent 300 Hz Gaussian noise draw gives 370 m error. Adding one seeded
satellite-specific epoch perturbation draw raises error to 1.48 km while held
RMS changes only from 321 to 326 Hz. These are conditional sensitivity examples,
not measured receiver accuracy or a noise-distribution accuracy guarantee.
The shared generator/fitter cannot detect common-mode physical-model errors.

A predeclared 20-seed extension retains that support and fits both starts for
paired noise-only and noise-plus-epoch cases (80 fits, all solver-success flags).
For independent 300 Hz noise, median/P90 error is 320/559 m and 45% of seeds are
below 300 m. The stipulated satellite perturbations raise median/P90 to
450/1,221 m, with 35% below 300 m. All perturbations use direct shifted-epoch
SGP4, not cached interpolation. These percentages describe the stipulated
synthetic noise model, not field reliability; both starts agree and must not
be counted as independent noise trials.

![Synthetic recovery controls](../2026_09_23_long_position_synthetic_control/synthetic_control.png)

A separate TRAIN-only local curvature audit explains a risk of adding timing
freedom. At the sealed zero-epoch baseline, profiling per-satellite epoch terms
with scale 5 s retains only 3.3% and 19.4% of the two normalized position
curvature directions; scale 0.2 s retains 78.3% and 84.7%. This is a local
Gauss–Newton objective diagnostic with fixed identities and cap membership,
not a calibrated position covariance and not a measurement at later fitted
optima. Lower residuals can accompany weaker localization.

![Curvature after profiling epoch effects](../2026_09_23_long_epoch_identifiability/profiled_curvature.png)

## Next evidence required

The complete first eight-hour TRAIN group now has a finished blind baseline
covering 72 scans and 3,587 tracks. The two starts yield 7.55 and 7.65 km error,
with about 312 Hz complementary-row capped RMS. Cache preparation took 6.77 s
and the two sequential prior searches took 1,897.59 s. This improves on the
roughly 10 km shorter-view baseline but does not establish sub-kilometre accuracy.
The six/sixteen views cover only about 35/107 minutes elapsed.
The full-group shared scan-epoch experiment improves error to 1.57 km at the
weakest tested regularization, with no timing-boundary or visibility failures.
All six arms meet a heuristic stopping rule, without certified stationarity.
These conditional fits retain the baseline identities, so alternating catalogue
reassignment and continuous fitting is the next direct test of that limitation.
One global epoch term instead of 72 independent scan terms gives 1.69–1.89 km
full-group error across all tested scales. Thus much of the localization gain
can be reproduced by a simpler model, although its held frequency RMS is worse
(about 303 Hz). The global fit reaches roughly −0.94 s at weak regularization;
this remains an empirical nuisance, not independent evidence of clock bias.
Synthetic success will not count as achieving the real-data accuracy objective.

The current experiment priorities are:

| Approach | Question it answers | Acceptance evidence |
|---|---|---|
| Full eight-hour joint blind baseline | Does more orbital diversity reduce the short-view bias? | Same fixed track policy and complete candidate search; both prior results sealed before reference evaluation |
| Regularized scan versus satellite epoch terms | Which structured mismatch explains residuals without absorbing position? | Bound-aware solver diagnostics, training-only fits, regularization sensitivity, and local curvature |
| Repeated synthetic noise controls | Was the single 370 m result representative under the assumed noise model? | Predetermined seeds, median/tail errors, both starts, no parameter selection by error |
| Joint identity reassignment after structured correction | Are fixed baseline IDs limiting the conditional models? | Full retained causal candidate pools, unchanged support, training-only reassignment and held checks |
| Frozen model comparison on independent groups | Do development gains generalize to different recording conditions? | All failures retained; group-level position error and residual metrics across 1/6/16/all-scan views |

The last two steps require completing the preceding TRAIN experiments first.
The final test must not become another model-development loop. Prior centres
are initialization/search constraints, not independent repeated datasets.

Before validation access, compare a small frozen set of complete model families
on TRAIN, including failures and convergence limits. A smaller frequency RMS
alone is insufficient evidence of geographic accuracy. Keep the final 64-scan
test group closed until model selection is complete.

## Reproducible evidence

- [Conditional epoch protocol, numerical results and source](../2026_09_23_long_shared_epoch_position/README.md).
- [Duration ablation, sealed outputs and plots](../2026_09_23_long_training_duration_ablation/README.md).
- [Association gap and loss audit](../2026_09_23_long_training_association_audit/README.md).
- [Satellite recurrence and gauge design](../2026_09_23_long_training_shared_satellite_epoch_design/README.md).
- [Loading and scoring performance checks](../2026_09_23_long_training_fast_score/README.md).
- [Full eight-hour cache manifest and receipts](../2026_09_23_long_training_cache_full8h/README.md).
- [Frozen train/validation/test manifest](../2026_09_23_long_inventory_complete/manifest.json).
- [Synthetic known-position control](../2026_09_23_long_position_synthetic_control/README.md).
- [Twenty-seed paired synthetic sensitivity](../2026_09_23_long_position_synthetic_multiseed/README.md).
- [Epoch versus position-curvature audit](../2026_09_23_long_epoch_identifiability/README.md).
- [Conditional satellite-epoch fits and solver diagnostics](../2026_09_23_long_satellite_epoch_position/README.md).
- [Full eight-hour blind baseline](../2026_09_23_long_training_full8h_position/README.md).
- [Full eight-hour conditional scan-epoch fit](../2026_09_23_long_full8h_shared_epoch_position/README.md).
- [Full eight-hour training residual concentration](../2026_09_23_long_full8h_residual_audit/README.md).
- [Fitted epoch versus host-timing semantics](../2026_09_23_full8h_tau_timing_semantics_audit/README.md).
- [One global epoch term across six/sixteen/seventy-two scans](../2026_09_23_long_global_epoch_position/README.md).

SOL implemented the epoch model; Terra audited associations, recurrence and
cache provenance. Root implemented the corrected duration inference and loading
equivalence check, reviewed the scientific invariants, and integrated reports.
All work uses existing recordings. No production deployment or RF collection is
part of these experiments.
