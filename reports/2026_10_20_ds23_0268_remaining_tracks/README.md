# DS23-0268: 53923, CH7 at 150 seconds and remaining unassociated tracks

All association colors refer to the saved receiver-step + family-reentry model: 2,111/3,165 GLRT points (66.70%). This investigation preserves the frozen ALGO02 sources and observations. Following TLEs are retrospective diagnostics only.

## 53923 orbit overlays

Green points belong to 53923, blue to another accepted satellite, red are unassociated. Black is the current causal phase/orbit-mode fit; orange is the causal nominal orbit at that phase; purple is the post-scan orbit at the same phase. Receiver/band calibration is included, every alias branch intersecting the native CFO range is drawn. The residual is modulo 227272.727 Hz; residual panels clip at ±3 kHz, while CFO panels show all GLRT points. No per-fragment constant is removed in these all-point overlays.

![RX1](53923_all_GLRT_RX1_c0.png)
![RX2](53923_all_GLRT_RX2_c0.png)

[Fitted-c RX1](53923_all_GLRT_RX1_fitted_c.png) · [Fitted-c RX2](53923_all_GLRT_RX2_fitted_c.png)

## CH7 T000: what fails

This is an intact single graph piece: 60 points, 120.559–177.344 s. A quartic polynomial gives 152.0 Hz RMS and lag-1 correlation 0.258, passing the residual screen. The current nominated family is 64333. At its independently refined phase, causal 64333 gives 193.4/194.1 Hz RMS (c0/fitted-c). Its lag-1 correlation is about 0.526; the n=60 limit is 4/sqrt(60)=0.5164. The existing shared prediction also has a mean error because the entire family was removed earlier and its nuisance parameters revert toward their priors.

The post-scan 64333 orbit gives 197.4/198.6 Hz and still fails. A nearby alternative, 69468, gives 190.6/191.9 Hz with post-scan elements and passes the local screen. Its c0 curve-score advantage over post-scan 64333 is only about 4.06, before phase priors and catalogue-search multiplicity: this is ambiguity, not an established new identity. All 1,402 candidates have a post-scan version; there is no fallback or candidate deletion. Epoch selection is earliest after scan end, earliest collection tie-break, fixed 48-hour window.

![CH7 orbit and residuals](CH7_150s_orbits_and_residuals.png)

## Independent receiver test and joint prototype

Ten accepted curved RX1 controls across five families fit an extra smooth receiver correction without any CH7 measurements. A 10-second-spaced, 15-second-width Gaussian basis (200 Hz coefficient prior; 300 Hz control-curve constant prior) predicts a correction of roughly -185 to -38 Hz on the target. The RF-scaled variant reduces CH7 RMS to 167.6/168.1 Hz; both local screens pass. Additive corrections give 169.1/169.6 Hz. An affine receiver correction does not help. These are conditional diagnostics, not a full covariance validation.

**Limitation:** removing 64908 from the extra-correction training loses the all-gate pass; other single-family removals retain it. Baseline calibration remains frozen in this leave-one-family diagnostic. Thus the evidence does not yet uniquely distinguish a receiver effect from 64908-specific orbital/calibration tension.

![Independent transfer](CH7_independent_receiver_transfer.png)

A full causal joint prototype replaces the original 30-second-spaced, 20-second-width RX basis with a 10-second-spaced, 15-second-width basis. Its amplitude is rescaled so average pointwise prior variance on the fixed 0–300 s grid equals the original. The exact Gaussian marginal volume penalizes added flexibility. Original GLRT, graph tracks, causal priors, weights, event time, cold regional start and search budgets are retained. Both original receiver/band nuisance sets remain; linear tracks never calibrate. This is one-scan development.

| Prototype | Paired gates | c0 / fitted-c error (km) | Associated GLRT, c0 / fitted-c |
|---|---|---|---|
| fine_kernel_CH7 | PASS | 5.216 / 5.273 | 2171 / 2171 |
| fine_kernel_CH7_alt69468 | FAIL | 6.261 / 6.457 | 2111 / 2111 |
| fine_kernel_baseline | PASS | 5.355 / 5.514 | 2111 / 2111 |

Current original-basis receiver-reentry baseline: 5.359/5.485 km, 2,111 associated GLRT in each arm. The finer-kernel 64333 prototype retains 2,171 (68.59%) in each arm, versus 66.70% before. The alternative 69468 fails even with the finer causal receiver kernel, so its post-TLE local pass does not transfer to a valid causal shared-parameter solution. Invalid rows are diagnostics, never accepted replacements. A successful CH7 retention does not solve the roughly 5 km location error. Geographic reference is read only here for error evaluation; no position is selected using it.

![Joint causal repair](CH7_joint_receiver_kernel_repair.png)

## Where the remaining evidence points

Unassociated total: 1054; 379 outside graph tracks; 334 in 21 nearly-linear tracks; 338 in eight wholly unassociated curved tracks plus three rejected points in an otherwise accepted curve. 19/21 nearly-linear tracks have a local catalogue/phase match, but an independently fitted phase is not a shared-family validation and linear tracks cannot calibrate.

| Track | Unassociated points | Causal best / RMS Hz / local pass | Post best / RMS Hz / local pass |
|---|---:|---|---|
| RX1-CH7-T000 | 60 | 64333 / 193.4 / False | 69468 / 190.6 / True |
| RX1-CH2-T005 | 62 | 67953 / 159.8 / False | 67953 / 156.4 / False |
| RX2-CH4-T000 | 3 | 60415 / 449.7 / False | 60415 / 451.9 / False |
| RX1-CH5-T005 | 49 | 66797 / 251.8 / True | 66797 / 254.3 / True |
| RX2-CH4-T001 | 46 | 69445 / 131.0 / True | 69445 / 139.7 / True |
| RX2-CH5-T001 | 53 | 59342 / 102.9 / True | 59342 / 103.0 / True |
| RX1-CH6-T004 | 25 | 64908 / 227.4 / False | 64908 / 226.5 / False |
| RX1-CH7-T003 | 25 | 63963 / 95.0 / True | 63963 / 93.7 / True |
| RX1-CH4-T006 | 18 | 66797 / 150.0 / True | 66797 / 150.5 / True |

![Remaining curved tracks](remaining_curved_track_gallery.png)

Local candidates are shape probes at the frozen RF position, with a Gaussian 1 kHz fragment constant and an independent phase searched over ±15 seconds. They do not include a phase prior in the ranking or new candidate orbit modes. The coarse grid is 0.25 s; the best four candidates are refined over ±0.3 s at 0.01 s resolution. No supplied evaluation coordinate enters either search. Local passes are not confirmed identities.

Eight original-basis causal joint re-entry trials were tested: each main family separately, 69468 as CH7 alternative, and all five locally passing curves together. None passes all original paired gates. 66797 and remapped 63963 conflict with retained 63901; 59342 and 67953 fail structured-residual gates; the extra 69445 curve conflicts with the shared family solution; 64333 and 69468 retain CH7 correlation/shape failures. A profile passing at its own phase can fail when phase/orbit/hardware parameters are shared with other tracks.

The current extension stage considers only already accepted curved-supported satellite families. Therefore a removed family such as 66797 or 59342 cannot recover through that stage, and the alternative 63963 nomination is never tried there. Original mask trimming plus frozen family nominations creates a recovery limitation. The strictly all-gate acceptance rule also couples useful proposals to marginal failures elsewhere; e.g. 63963 re-entry causes retained 63901 slope statistics of 3.006/3.019 against a limit of 3.

## Nearly-linear fragments: candidate inventory

A concrete excluded family is 69238: RX1 CH2 T007, CH3 T006, CH7 T005 and CH8 T004 contain 53 points at 17–30 s. Independent local probes choose phases around -1.5 s for all four. There is no accepted curved anchor for that satellite, so the existing extension stage cannot try it. This is useful corroboration, but it does not authorize using these tracks to recalibrate receiver offsets/drifts. A predictive catalogue association stage can test such families with radio/position calibration frozen and causal orbit uncertainty integrated. The candidate lists below are diagnostics, not confirmed associations.

| Fragment | Points | Time s | Best locally passing candidate, or best failed candidate | RMS Hz | Local pass |
|---|---:|---|---:|---:|---|
| RX2-CH1-T005 | 8 | 257.6–282.1 | 63901 | 106.8 | True |
| RX1-CH1-T003 | 26 | 35.8–60.0 | 68396 | 82.8 | True |
| RX1-CH4-T008 | 13 | 122.2–145.6 | 63963 | 172.1 | False |
| RX2-CH3-T002 | 11 | 40.2–59.7 | 63913 | 484.2 | False |
| RX2-CH2-T001 | 10 | 41.6–60.0 | 57780 | 173.3 | True |
| RX2-CH4-T002 | 21 | 270.2–284.4 | 65699 | 20.8 | True |
| RX1-CH4-T002 | 22 | 210.2–224.4 | 59342 | 147.3 | True |
| RX1-CH8-T002 | 19 | 0.7–14.9 | 57718 | 115.0 | True |
| RX1-CH5-T000 | 20 | 210.6–224.8 | 59342 | 110.8 | True |
| RX2-CH1-T003 | 22 | 0.0–14.2 | 69455 | 86.0 | True |
| RX2-CH1-T002 | 22 | 45.8–60.0 | 57718 | 45.9 | True |
| RX1-CH7-T007 | 16 | 210.7–224.5 | 66191 | 122.1 | True |
| RX1-CH2-T007 | 18 | 16.0–29.9 | 69238 | 94.7 | True |
| RX2-CH3-T001 | 19 | 1.5–14.3 | 59890 | 74.1 | True |
| RX1-CH8-T004 | 8 | 16.6–29.4 | 69238 | 50.3 | True |
| RX1-CH3-T006 | 11 | 17.5–29.9 | 69238 | 81.1 | True |
| RX1-CH6-T007 | 15 | 32.9–44.9 | 68325 | 109.7 | True |
| RX1-CH1-T007 | 12 | 0.0–12.1 | 62014 | 120.6 | True |
| RX2-CH1-T004 | 16 | 62.1–74.2 | 66081 | 139.8 | True |
| RX1-CH7-T005 | 16 | 17.3–29.4 | 69238 | 146.5 | True |
| RX2-CH8-T001 | 9 | 166.7–177.4 | 51813 | 144.9 | True |

## Recommendation

Retain the intact CH7 curve as evidence. Evaluate the normalized finer receiver covariance on other scans, with c0/fitted-c and independent-family transfer controls. Keep multiple nearby identities when they are not distinguishable. Add a bounded catalogue re-nomination/re-entry stage for rejected curved families, then require joint shared-parameter consistency. Do not weaken noise gates or declare identities from visual alignment alone. The 379 points outside graph tracks require a separate graph/alternative-peak audit; they were not proven to be clutter by this study.

## Reproduction and provenance

Run with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python`: `tools/investigate_ds23_0268_remaining_tracks.py --stage inventory`, `banks`, `screen`, `refine`, `reentry`, `alternate`, `transfer`, `kernel`; render `tools/plot_ds23_0268_remaining_tracks.py --stage orbit` and `screens`; then `tools/report_ds23_0268_remaining_tracks.py`. Export postscan elements first through the read-only adapter `tools/export_ds23_postscan_tles.py --directory reports/2026_10_19_algo02_ds23_full/DS23-0268`. Archive reads require the existing archive permissions. No new RF collection or IQ remeasurement occurred.

Machine-readable receipts: [inventory](inventory.json), [candidate table](curved_candidate_summary.csv), [causal refined search](causal_refined.json), [post refined search](postscan_refined.json), [following TLE provenance](postscan_tles.json), [receiver transfer](CH7_independent_receiver_transfer.json), [kernel coverage](kernel_coverage.json), [re-entry execution](reentry_execution.json).
