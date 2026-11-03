# DS26 / DS27: investigation of all 20 longest residual GLRT tracks

2026-10-31 · `find-glrt-association` · numerical source revision `a9a340309a004d31f133e59662c24414a6a71b22`

We investigated the ten longest post-ALGO05 residual fragments in each dataset: **20 sources, 16 scans, 1,546 unique native GLRT points**. All selected fragments occupy one original polynomial piece. Missing catalogue members and bounded phase search explain three particularly poor matches; several other identities are supported but still have structured residuals. A small residual alone does not establish a unique satellite.

**No new point ownership was accepted, no position was refitted, and production was not changed.** The comparisons below diagnose association failures at the published per-arm position. They do not demonstrate a localization improvement.

## Main findings

| Source | Finding | Controlled causal result |
| --- | --- | --- |
| DS26-0068 RX1 CH7, 91 points | NORAD **58538** was excluded by the 48-hour element-age cutoff; its available-before-scan element was **52.12 hours old**. The prior 63573 nomination was conditional on an incomplete candidate catalogue. | A general 72-hour catalogue search reduces best-fit RMS **1,176 → 119 Hz**, with phase −0.89 s and only +0.28 Hz/s extra rate. Residual correlation still fails. |
| DS26-0062 RX1 CH3, 86 points | NORAD **67821** was similarly excluded; its causal element was **50.65 hours old**. | General 72-hour search reduces RMS **1,130 → 63 Hz** at phase −7.81 s. The diagnostic noise checks pass in both c arms. New independent nomination and exact inclusion validation remain necessary. |
| DS26-0134 RX1 CH5, 96 points | NORAD **59642** is already in the causal catalogue but needs phase **−27.18 s**, outside the ±15 s search. | General ±35 s search reduces the best causal RMS **930 → 75 Hz**. Increasing catalogue age alone does not fix it. The later-TLE search independently nominates the same satellite. Residual correlation remains. |
| DS27-0002 RX2 CH8, 64 points | Fresh search nominates **100427**; no retained independent nomination existed in the previous inventory. The inherited family already has **85 active support points**. | Its existing shared phase and physical orbit correction predicts this target at **16.2 Hz RMS** (17.0 Hz in c=0), passing the diagnostic noise checks. A target-only simplified model gives 62 Hz. Reusing the correct shared model matters. |
| DS27-0018 RX1 CH8, 40 points | **58121** is a promising new candidate; the historical recovery output was incomplete. | About **106 Hz RMS**, passing isolated diagnostic checks. There is no independent active family support, so this is a nomination, not a confirmed association. |
| DS27-0020 RX1 CH1, 70 points | **67344 versus 50173 remains ambiguous.** | Broadening phase collapses the isolated score margin from about **289 to 1.5**, even though 67344 stays first. Broader search also prevents false confidence. |

These three general age/phase remedies were tested on **all 20 sources**, not only on the sources that suggested them. The other 17 first-ranked identities remained unchanged in the matched 2×2 comparison. Some competitor margins narrowed substantially. This is a conditional search diagnostic, not a blind dataset-wide acceptance result: the new bounds were proposed after examining this cohort.

![Controlled causal age and phase comparison](figures/age-phase-ablation.png)

## Every source, with qualified identity assessment

See [the complete 20-source findings table](findings.md), [CSV](best_associations.csv), and [JSON](best_associations.json). The table distinguishes independent identity support, model mismatch, and ambiguity. It includes the newly discovered age/phase explanations, rather than preserving the original incomplete-catalogue winners as answers.

![Best causal diagnostic fits and independent shared predictions](figures/best-causal-fit-summary.png)

The [track atlas](track_atlas.md) contains a native GLRT dashboard and consecutive **20-second zooms for every source**. Each source also has a `*-support.png` companion under [figures](figures), showing causal/later candidate-model comparisons and receiver/family attribution. Gray points in native context plots are explicitly labeled **published associated**, not unassociated.

## What resolves uniqueness, and what does not

DS27-0020 CH4 illustrates the distinction. When each candidate can choose a track-specific phase, **61549 and 62146 both approximate the curve**. With the phase and physical correction learned from independent tracks, the target residual is **104 Hz for 61549 versus 4,727 Hz for 62146**. The shared family evidence supports 61549 even though target-only randomized folds can favor 62146. The residual curvature/step failure remains a separate model-adequacy issue.

![Independent support separates plausible isolated curves](figures/DS27-0020-RX1-CH4-T005-support.png)

DS27-0002 CH8 is the clearest candidate for an additive recovery using an existing calibrated family:

![Existing shared model explains the unsearched CH8 curve](figures/DS27-0002-RX2-CH8-T001-support.png)

Other sources remain ambiguous: DS27-0022 CH4 has 59737/54159 competition in randomized groups; DS27-0012 CH2 has 57999/63782 competition despite a roughly 22 Hz best RMS; DS27-0020 CH8 prefers 55430 here but previous independent nominations alternated with 51969. We do not convert profile-score gaps into identity probabilities.

## Why the remaining sources are not automatically recoverable

- Many favored satellites already have independent family evidence, but their target residuals contain correlation, curvature, or steps. Later TLEs do not consistently remove those features.
- The two catalogue-age omissions are causal input-selection failures. This is different from asking an incorrect satellite to absorb a curve through calibration.
- The DS26-0134 failure is a phase-search truncation. It motivates physically informed search expansion and wider orbit-bank support, not an unpenalized phase adjustment for every track.
- DS26-0251 requires about **−11.7 Hz/s** additional rate to get a 153 Hz isolated fit. That exceeds the intended small-drift regime, and no independent active family supports it. A clean-looking curve is insufficient justification for adding this correction to the receiver.
- Target-only constant/rate controls are lower-bound diagnostics. Their fitted rates cannot be assigned to a receiver or satellite without shared evidence. Receiver/family attribution plots show the available overlapping controls, but this run does not establish a general new hardware correction.
- No selected residual fragment crosses multiple original polynomial pieces. An upstream wrong join is therefore not the common explanation for this inventory. The saved alias transitions are retained and plotted; alternate native-peak reconstruction was not performed.

## Experimental design

### Ownership and position

Inputs are the sealed `reports/2026_10_31_algo05_promotion/residuals/{DS26,DS27}-top10.json` inventories. We reconstructed the chosen published ownership, compared it with the frozen plot packet, and checked that every selected native ID is unassociated. None of the 20 targets contributes active calibration observations in the inherited model.

The inherited baseline objective replays with zero recorded discrepancy in both c arms. We then recondition that inherited radio model at each **published ALGO05 endpoint**, keeping target evidence excluded. This is not a replay of every added ALGO05 correction: the inherited calibration model and its conditioning are explicitly recorded. Existing accepted owner sets remain fixed. Original baseline and published endpoints are saved in each scan receipt.

No evaluation GPS was used. This report does not explore the regional position basin or claim position improvement. Full acceptance would require a matched joint refit, exact ownership replay, and subsequent position evaluation.

### TLEs and search coverage

The original causal banks contain 1,249–1,700 regionally eligible satellites. Per-element provenance checks require both element epoch and collection time to precede the causal cutoff. The original catalogue preparation imposes a 48-hour age window and a broad regional visibility filter, with no satellite whitelist.

The later bank uses the **first archived availability of a post-scan-epoch TLE within 48 hours after scan end**, independent of RF score. We read 110 relevant archived snapshots. It includes candidates outside the original causal banks. For the newest scans, the archive has not yet accumulated all first-post-epoch elements; **eight of the original 20 causal winners lack an eligible later counterpart**. A different satellite winning such an incomplete later search does not refute the causal identity. No missing later element is silently replaced with a causal one.

The follow-up causal audit read 309 snapshots and checked pre-scan availability for the finalists. The expanded experiment independently rebuilt the **complete Starlink causal catalogue with a 72-hour window**, without an RF-selected identity list, and compared 48/72-hour eligibility and ±15/±35-second phase bounds. Propagation failures are recorded explicitly in expanded-search outputs, not treated as satellite mismatches.

Search screens every available bank candidate on a coarse phase grid, with horizon checks. The union of finalists across models, c arms, and TLE banks receives exact full-point phase optimization. The initial candidate nomination uses 16 representative native times; the expanded nomination uses two-second phase spacing. This is broad catalogue screening plus exact shortlist fitting, not exhaustive continuous optimization of every satellite. Scores and confidence are conditional on that search coverage.

### Nuisance models and polynomial audit

All fits retain the inherited shared receiver/band hardware correction, frequency scaling, and receiver smooth terms. Four additional **target-only diagnostic controls** are compared:

| Model | Phase prior / bound | Constant prior sigma | Extra-rate prior sigma |
| --- | --- | ---: | ---: |
| Phase + offset | Gaussian 5 s; initially ±15 s | 300 Hz | fixed zero |
| Phase + small rate | same | 300 Hz | 0.5 Hz/s |
| Phase + wider rate | same | 1,000 Hz | 2 Hz/s |
| Affine control | same | 1,000,000 Hz | 30 Hz/s |

These are declared research priors, not a claim that production uses the same phase distribution. The affine control is not an admissible hardware solution. The score includes squared residuals at a fixed 150 Hz scale, Gaussian prior pulls, and the linear-Gaussian normalization/complexity terms from `profile_rate`. Phase is optimized with a prior penalty rather than fully marginalized. Residual correlations therefore limit the interpretation of these approximate profile-score differences.

We separately test (a) the original independently calibrated shared phase and physical orbital modes, and (b) phase and a shared frequency rate fitted only to independent active curves from the same family. A target may profile a 300 Hz constant but does not calibrate those shared terms. No six-element orbit solution or new mean-motion optimization was attempted. A free target rate does not prove TLE error.

Polynomial degrees 1–4 use the existing robust clutter/complexity estimator; ordinary degrees 0–4 are retained as controls. Native points, endpoint sensitivity, active curvature, full/retained RMS, and residual diagnostics are preserved. Reported diagnostics include mean, slope, quadratic gain, step, and lag-one correlation. In-sample mean and slope after fitting those terms are not independent identity evidence. The diagnostic checks are not a substitute for the exact production acceptance gates.

### Predictive checks and c ablation

The initial finalists receive reproducible random whole-12-second-group checks with a two-second guard, using seeds 20261031, 94721, and 4081. The graph, inherited calibration and finalist shortlist were already selected using existing data, so these checks are **conditional stability tests**, not unbiased new identity-validation results. Historical independent nomination results are labeled separately. Expanded-catalogue nominees still require fresh independent validation.

All search models, finalist unions, native observations, and budgets are matched between **c=0 and fitted-c**. Each arm uses its own published endpoint and conditioned calibration. The data preserve both arms; the main tables show fitted-c for readability. These comparisons are conditional model-state comparisons, not an isolated causal estimate of changing c while holding position fixed. No frequency-fit gain is described as a localization gain.

## Recommended next experiments

1. **General catalogue-age recovery:** retain the usual recent bank, but offer 48–72-hour causal elements with age-dependent physical uncertainty when a long curved residual has no adequate recent-bank candidate. Test 67821 and 58538 with training-only nominations and exact additive owner replay. Do not bake these NORADs into the algorithm.
2. **Bound-aware phase expansion:** widen search and propagation support when the bounded fit or causal TLE disagreement justifies it; penalize the added range and retain competitors. Test 59642, while explicitly monitoring the newly close 67344/50173 alternative.
3. **Existing-family inclusion:** test DS27-0002 CH8 against the already learned 100427 shared model, then require no lost incumbent owners and paired-c acceptance. Investigate DS27-0018’s incomplete recovery separately.
4. **Structured-residual diagnosis:** on supported identities such as 66102, 58788, 64172, 61549 and 57914, compare synchronized residual structure across receivers/bands and revisit CFO estimation covariance. Add a shared correction only if independent tracks predict its sign, timing, and magnitude. A lower RMS or larger association percentage alone is insufficient.

## Reproduction and artifacts

The [run manifest](run_manifest.json) records source/data hashes, numerical code revision, parameter settings and replay results. The [controlled ablation CSV](age_phase_ablation.csv), [original candidate fits](candidate_fits.csv), per-scan `expanded_search.json`, `shared_competitors.json`, and per-source arrays permit regeneration of the figures without new RF collection.

All scripts are in [reproduction](reproduction). Execute with the recorded numerical checkout's Python and `PYTHONPATH=src:tools`. Archive exports require read access to `/var/lib/leo/tle` and use the existing read-only archive adapter. The archive and QNAP were not modified. Pipeline implementation and deployment were unchanged.

Execution order: `archive_export.py`, `investigate.py --case ...` (six independent case processes), `audit_causal_catalogue.py`, `followups.py`, `shared_competitors.py`, `export_causal72.py`, `expanded_search.py`, `render.py`, `supplement.py`, `conclusions.py`. Tests are in `reproduction/test_investigate.py`.
