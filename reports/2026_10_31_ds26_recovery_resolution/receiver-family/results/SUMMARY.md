# DS26-0050: receiver correction with whole-family exclusion

**The stronger independent test has insufficient temporal/family support to establish a robust target correction.** Every full 77-point target evaluation fails unchanged residual gates in both c arms and all three folds. Removing all target-family RF evidence also leaves its phase/orbit weakly identified, so the larger residuals do **not refute a receiver mechanism**. The earlier approximately 117→100 Hz gain is not yet independently robust. This test retains the original candidate/alias nominations as an explicit condition.

## Protocol and independence

Seed **20261031** randomly partitions all **16 eligible non-target NORAD families** into three disjoint held-family folds:

| Fold | Held NORADs |
|---|---|
| 0 | 57791, 59749, 60259, 63467, 67824, 69529 |
| 1 | 53783, 62054, 62825, 67446, 67953 |
| 2 | 58866, 60275, 63481, 63487, 67934 |

**All NORAD 63468 observations**, across receivers/channels and including predictive entries, are excluded from every training fit. Each fold also removes its held families everywhere. Position, phase and receiver are refitted using only the remaining curved observations and predictive position entries, from the same regional **[0,0] km** start in the **±12.5 km** box. Both c = 0 and fitted-c receive the same five phase rounds × 48 position steps, observations, identities, aliases, TLE priors, fixed 150 Hz preprocessing, and unit family weights. Full-data RF noise selection is disabled for curved and predictive training alike. Observation-ID uniqueness and train/evaluation disjointness are asserted.

One prespecified receiver-only correction is fitted to training residuals: RF-scaled Gaussian basis functions, **6 s width and spacing**, independent coefficient blocks for RX1/RX2, **150 Hz coefficient prior**, **150 Hz witness noise**, and **300 Hz per-track nuisance prior**. No target or held values enter this fit. No length-scale/noise/prior alternative was tried. The applied correction is zero unless at least **two distinct training families on the same receiver lie within 18 s**; unsupported times retain an explicit flag and the unapplied model forecast.

Original graph candidate/alias nominations were produced in earlier full-data work, so this is a **conditional nomination test**, not fresh identity discovery. Held-family and target phase/orbit states use their causal priors rather than target/held RF fits. Evaluating an existing per-track nuisance constant is allowed equally before/after; it never updates geometry or correction. No GPS, future TLE, RF collection, production change, or association acceptance is involved.

## Matched target results

Each numeric pair is **c = 0 / fitted-c**. RMS is in Hz; both arms use the same supported points.

| Fold | Before RMS | After RMS | Support | After lag-1 ACF | Full-track failed gates |
|---|---:|---:|---:|---:|---|
| 0 | 202.86 / 233.73 | 204.25 / 234.83 | 14/77 | .886 / .908 | Slope, quadratic, step, ACF; both arms |
| 1 | 114.55 / 124.11 | 110.10 / 113.44 | 53/77 | .649 / .668 | c0: step, ACF; fitted-c: ACF |
| 2 | 379.50 / 440.80 | 379.50 / 440.80 | 0/77 | .943 / .949 | Slope, quadratic, step, ACF; both arms |

All target RMS, offset, visibility and frozen-alias gates pass, but this does not override the residual failures. The unchanged noise limits are mean z ≤ 3, slope z ≤ 3, quadratic BIC gain ≤ 10, maximum step z ≤ 4, and |lag-1 ACF| ≤ **4/√77 = .455842**. The full target is the endpoint, not a favorable supported subset. Fold 0's 14 supported points happen to pass their subset gates; **63 target points lack support**. Fold 1's supported subset still fails ACF in both arms. Fold 2 supplies no supported target prediction, and its correction is therefore zero.

Training-only endpoints are **(3.637, −6.885) / (4.007, −6.734)** km in fold 0; **(2.931, −8.877) / (3.541, −8.879)** in fold 1; and **(5.772, −8.240) / (6.454, −8.113)** in fold 2. These are inference coordinates, not position errors. No position truth or accuracy comparison was made.

Training-fit settling is reported separately from held predictive performance. Cells are c0 / fitted-c; objectives compare neither folds of different sizes nor position accuracy. These checks show the fixed phase-reference iterations settling, not a global-optimum certificate.

| Fold | Final training objective | Last-round position movement, m | Final phase-reference change, ms |
|---|---:|---:|---:|
| 0 | 15823.94 / 15827.80 | 2.911 / .299 | .448 / .049 |
| 1 | 24357.94 / 24360.97 | 2.527 / .911 | .383 / .140 |
| 2 | 20295.88 / 20295.14 | 1.187 / .323 | .180 / .050 |

All six arms completed in **17.99 s total** under the 570 s execution limit with one numeric thread. **Four tests passed.**

## Independent held families and covariance interpretation

The table shows every family whose pooled held residual RMS worsened in both arms. Cells are **before→after**, c0 / fitted-c, in Hz. Complete results for all 16 families, including track-level regression counts, are in [held-family-summary.csv](held-family-summary.csv).

| Fold | Held NORAD | c = 0 | Fitted-c | Supported/total points |
|---|---:|---:|---:|---:|
| 0 | 59749 | 109.87→110.39 | 117.67→119.17 | 18/18 |
| 0 | 69529 | 1442.67→1443.53 | 1426.24→1427.56 | 116/282 |
| 1 | 67446 | 568.36→571.78 | 554.28→557.68 | 19/19 |
| 1 | 67953 | 1135.04→1136.66 | 1105.38→1106.28 | 103/120 |
| 2 | 60275 | 146.51→151.07 | 135.69→140.01 | 69/147 |
| 2 | 63487 | 350.16→351.51 | 313.48→313.90 | 150/150 |

Some families improve modestly: fold-0 NORAD 60259 changes **118.24→114.95 / 116.39→112.56 Hz**, supported at **242/403** points; fold-2 NORAD 63481 changes **729.94→701.54 / 753.63→724.28 Hz**, supported at **48/71** points. NORAD 58866 is unsupported throughout its 91 held points, so it receives no correction. Large held-family errors can remain because their phase/orbit and position relationship is deliberately untrained; these are not isolated receiver-noise measurements and cannot refute a receiver contribution.

Independent receiver/band summaries also show mixed transfer, rather than a universal receiver explanation. Fold-0 RX1 lower-band pooled RMS worsens **1193.76→1194.06 / 1183.68→1184.35 Hz**, while RX1 upper band improves **180.53→175.72 / 189.46→184.37 Hz**. Fold-2 RX2 upper band worsens **490.33→493.26 / 475.94→478.44 Hz**. The model does not fit band or satellite corrections, so these contrasts diagnose inconsistency; they do not select a band model or identify a causal source. See [receiver-band-summary.csv](receiver-band-summary.csv).

## Uncertainty, limitations and minimal next experiment

Target correction-only posterior standard deviations are approximately **54.83, 52.45 and 59.33 Hz** by fold, identical across arms because correction design/noise are matched. These are conditional empirical Gaussian uncertainties. Including the untrained target family yields median approximate total prediction standard deviations of **15.83–15.93 kHz**. Consequently the descriptive 95% marginal coverage is 100% in every arm and is **uninformative**, not validation. The approximation excludes position uncertainty, nonlinear orbit/phase effects, learned precision uncertainty and cross-covariance between baseline and correction estimates. Plots show correction-only bands explicitly; unsupported model forecasts are retained separately and never applied silently.

Family exclusion reveals a support and identifiability problem before it proves that 6 s smoothing underfits. Remaining target ACF cannot distinguish rapid receiver variation, satellite phase/orbit error, band effects, or target-specific structure. Better frequency fit in fold 1 establishes neither a recovered association nor improved localization. Three folds share observations across training sets and are not independent replications.

The next parsimonious experiment should retain **independent NORAD63468 observations on RX2 as orbital/phase witnesses**, while keeping the target RX1 CH1 curve untouched and excluding all NORAD63468 observations from receiver-correction fitting. The orbital witness must use a separate receiver posterior learned from other training families, with its uncertainty propagated; it must not silently calibrate the target receiver. Hold other families out of calibration and correction across all channels/receivers, retain a common regional start and matched c arms, and establish temporal support before interpreting a target change. This separates missing satellite-state information from receiver transfer, if the available witnesses identify both.

A complementary cheap diagnostic is a **matched receiver difference-of-differences** before adding model flexibility. For two independently held satellite families observed on both receivers, form simultaneous RF-normalized RX1−RX2 residual contrasts using unique one-to-one time pairs. A satellite-common orbit/phase error cancels approximately within each family; agreement of receiver contrasts across families would support a receiver effect. Repeat within matched bands to test whether it is common or band-specific. Predeclare timing tolerance, whole-family/frame grouping and minimum independent-pair support; do not tune them on the target curve. Sparse overlap is a valid negative result.

Only if independent witnesses establish a shared sub-6 s covariance feature should a single faster alternative be considered: a 2 s piecewise receiver term with the **same 150 Hz prior**, validated on whole held families/frames before touching the target. This is a proposed experiment, **not a fitted result**. Shrinking smoothing width just to whiten the target would not resolve attribution. No additional fit was performed.

Artifacts: [protocol](protocol.json), [target table](target-summary.csv), [complete results](result.json.gz), [source hashes](sources.json), [target before/after plot](target-before-after.png), [held-family plot](held-families.png); PDFs accompany the plots. Sources are the prior DS26-0050 orbit diagnostic and frozen trial/inventory identified by path and SHA-256 in the protocol. Study scripts and tests are in the parent directory.
