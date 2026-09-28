# Positioning and receiver-geometry experiment log

## Scope and reading rules

This log reconstructs the positioning thread from persisted reports: DS5 timing
and association work, joint-location prototypes, and the later roof
receiver-geometry experiments. It excludes unrelated RF acquisition and decoder
optimization. “Reference” means the known/operator-supplied receiver location;
for the roof work it is explicitly not surveyed GPS. Candidate satellite IDs
are model associations, not decoded physical truth.

Results are not interchangeable. Early DS5 tables often compare likelihood at
three fixed sites; later tables report geographic distance after a search; roof
tables use exact fixed local grids. Eight Sacramento/Reno cases in the roof
cohort are only four recordings. Development, retrospective, and already
unblinded results are labeled as such. Historical results that reused candidate
proposals across locations are segregated below because their apparent location
gains are not valid independent-prior evidence.

## 1. DS5: timing was useful, but association dominated failures

The initial probabilistic DS5 evaluation compared zero timing, independent
per-track timing, shared-satellite timing, an element-age prior, and a scan
clock across 42 recordings. On the 41 scans excluding the development example,
the age-shared model preferred the reference over Sacramento in 25/41 scans
(mean NLL gap -0.0541) and over Reno in 28/41 (-0.1231). A scan clock barely
changed those values. Independent timing reduced RMS from roughly 464 Hz at the
reference under zero timing to 279 Hz, but better residual fit did not translate
cleanly into location discrimination. The six large-error scans remained mixed:
08:50 actually favored the wrong Reno site by +1.0363 NLL under age-shared
timing, while several other catastrophic Reno errors favored the reference.
This rejected the simple story that a single clock correction explained the
geographic failures. Source: [DS5 probabilistic report](sources/2026_09_26_ds5_probabilistic/REPORT.md).

The empirical timing-prior follow-up used all 42 scans and frozen historical
timing distributions. Its joint model lowered reference mean RMS to 194.2 Hz
and preferred the reference 30/42 times against Reno and 27/42 against
Sacramento. Adding a scan clock again changed almost nothing. Extending the old
timing range to ±60 seconds also barely affected rankings. This supported a
calibrated timing nuisance, but not a timing-only solution. Source:
[empirical-prior aggregate](sources/2026_09_26_ds5_empirical_prior/aggregate.json).

The focused 08:50 diagnosis exposed the mechanism. Tracks frozen to two
satellite IDs required mutually incompatible corrections (roughly -17 to +4 s
inside one group). Original frozen assignments scored 8.364 NLL/observation at
the reference versus 7.227 at wrong Sacramento. A bounded training-only joint
assignment/shared-timing update changed the ordering: reference 6.588 versus
7.157/7.254 at the wrong sites, and reference RMS fell from 1,271 to 395 Hz.
Independent reassignment followed by timing pooling was worse—4,172 Hz—because
it ignored the cost imposed on tracks already assigned to the same satellite.
The required +42 s and -17 s corrections were extreme under the age prior, so
the new IDs were not accepted as physical truth. Accepted lesson: association
must be inside the shared-latent model. Rejected lesson: merely widening timing
bounds or hard-reassigning tracks. Source:
[08:50 diagnosis](sources/2026_09_26_ds5_0850_diagnosis/REPORT.md).

An unrestricted residual-polynomial stress test showed why residual RMS alone
could not authenticate IDs. Quadratic/cubic corrections brought competing IDs
to tens of hertz, but sometimes required 12 kHz correction excursions. Flexible
polynomials absorbed the very Doppler shape needed for association. This was a
diagnostic rejection of unconstrained polynomial cleanup, not a deployable
model. Source: [residual-polynomial report](sources/2026_09_26_residual_polynomial/REPORT.md).

## 2. Soft association and joint location

The bounded soft-association prototype examined six known failure scans.
Soft temperatures 5/10/20 produced the same selected locations as hard
assignment. A <10 Hz ambiguity rejection did not identify the failures: the
08:50 scan had only 3/39 low-margin tracks despite a 123.5 km Reno error.
Candidate stability was generally high across mask splits, so simple entropy or
margin gating was not a sufficient safety mechanism. Source:
[soft-association prototype](sources/2026_09_26_association_soft_prototype/REPORT.md).

The later deterministic independent-soft evaluation extended exact,
training-only satellite/timing marginalization to all 42 DS5 scans. It produced
30/42 known-site wins against each of the Sacramento and Reno estimates and
24/42 wins against both, with mean known-minus-estimate gaps of -0.1536 and
-0.1358 NLL/block. It removed sampler instability, but remained
development-corpus evidence with dependent train/evaluation blocks and no
geographic search. A chronologically later 60d9 scan was an informative single
case: soft assignment rejected the catastrophic 551.9 km Reno branch but still
preferred the nearby 5.79 km branch over the reference. That supported
basin/association repair, not sub-6-km resolution. Sources:
[independent-soft report](sources/2026_09_26_independent_soft/REPORT.md) and
[60d9 held-out review](sources/2026_09_27_scan_60d9d1e77c14da0a/REPORT.md).

Some historical “shared-proposal hard” results changed enormous Reno errors to
the Sacramento-prior answer—for example 428 and 676 km became 5.79 km. Those
numbers are useful evidence that candidate inventory/search coverage mattered,
but they are **not valid location gains**: candidate proposals originating from
one location were reused at another, violating independent-prior construction.
They must not be cited as geographic accuracy improvements. The valid soft
prototype conclusion is the negative one above: soft weighting alone did not
move the independently evaluated solutions.

The joint-location prototype forced three adjacent scans to share one location.
It reduced the two selected failure groups from independent mean/worst errors
49.6/123.5 km and 239.2/706.8 km to shared errors 5.00 and 3.99 km. Random groups
landed at 5.79 and 6.53 km. This demonstrated that repeated scans can constrain
a common receiver location, but the groups were retrospective and the shared
coordinate can be dominated by neighboring scans; it did not prove per-scan
resolution. Source: [joint-location prototype](sources/2026_09_26_joint_location_prototype/REPORT.md).

The full joint-mixture experiment evaluated all 42 scans with shared candidate
identity/timing mixtures. At 100 Hz, the joint model preferred the reference in
28/42 comparisons against Reno and 31/42 against Sacramento, with mean gaps
-0.1849 and -0.1688. On the six ≥100 km Reno failures it won 5/6. But inference
was fragile: 10/42 scans had different chain winners and 28/42 had maximum
assignment total variation above 0.9. At 200 Hz the score gaps shrank and some
wins disappeared. This was predictive evidence for joint marginalization, not
stable decoded identities. Sources: [joint-mixture report](sources/2026_09_26_joint_mixture/FULL_DS5_REPORT.md)
and [full summary](sources/2026_09_26_joint_mixture/full_summary.json).

A deterministic assignment-change penalty reduced reassignment counts but did
not materially improve discrimination. The primary log(12) penalty yielded
reference wins 28/42 versus Sacramento and 26/42 versus Reno, compared with
27/42 and 30/42 unpenalized. It regularized behavior, not accuracy, and was not
promoted. Source: [penalized-joint report](sources/2026_09_26_penalized_joint/REPORT.md).

## 3. Transition to roof data and receiver geometry

The roof program separated calibration from four development recordings and
preserved independent Sacramento/Reno priors. Source-topology collisions led to
whole-track exclusions and consistent refits rather than selective outcome
removal. The initial direction-subset reception test was encouraging:
detection log loss improved from 0.6534 to 0.4791 and conditional ratio MSE from
0.3217 to 0.1738 on four held scans; all four detection scans improved. Long
tracks and matched-rate sensitivity retained the gain, while direction shuffle
and reversal controls were worse. This established reception prediction, not
geographic accuracy. Sources:
`reports/2026_09_27_roof_direction_subset/results.json` and
`reports/2026_09_27_roof_direction_subset/REPORT.md` where present.

The first geographic searches mixed two issues. A Gaussian 100 Hz frequency
model was too light-tailed for calibration residuals (known-site MAP RMS roughly
p10/median/p90 57/156/474 Hz), and the adaptive search had a boundary-priority
bias. Neither alone explained all failures. A robust Student-t frequency model
was calibrated on six scans, and later search work distinguished search coverage
from likelihood ranking. These steps were necessary numerical/model hygiene,
not evidence that RX geometry improved location. Sources:
`reports/2026_09_27_roof_location_geometry/ROBUST_PROTOCOL.md`,
`reports/2026_09_27_roof_location_geometry/topology_frequency_fixedpoint.json`,
and the saved search artifacts.

The FIRST four-recording confirmation gave a striking but nonuniform result:
joint geometry improved two cases, worsened four, and tied two. Sacramento mean
error fell from 141.329 to 67.523 km, dominated by f147 moving from 319.933 to
0.613 km, while Reno mean worsened from 198.213 to 198.967 km. The frozen
secondary improved one, worsened one, and tied six. Diagnostic union-of-points
ranking showed that Doppler also preferred the recovered f147 point, so the
headline gain was search coverage, not uniquely directional evidence. A
post-unblinding depth-balanced repair confirmed this: at the same 160-point
budget, Doppler alone improved three cases, worsened one, and tied four,
including the same f147 recovery and a catastrophic 609d Reno repair. Geometry
under that repaired search improved three, worsened two, and tied three, with
its largest remaining gain again attributable to coverage rather than fine
resolution. Sources: [FIRST confirmation](sources/2026_09_27_roof_geometry_confirmation/RESULTS.md)
and [depth-balanced development](sources/2026_09_27_roof_geometry_confirmation/BALANCED_DEVELOPMENT_RESULTS.md).

The depth-balanced policy was then frozen on a SECOND, outcome-blind four-scan
cohort. Primary geometry improved two prior cases, worsened one, and tied five.
Overall mean error moved from 4.711 to 4.592 km, but median error worsened from
5.371 to 5.611 km; Reno mean improved from 5.239 to 4.811 km while Sacramento
mean worsened from 4.182 to 4.372 km. The secondary improved one case and tied
seven. This was a valid matched result, but four recordings and mixed
directions did not establish a population-level resolution gain. Source:
[SECOND confirmation](sources/2026_09_27_roof_balanced_confirmation/RESULTS.md).

Only after unblinding, an exact local-grid diagnostic on that SECOND cohort
found that the matched primary and reciprocal-pair-deduplicated runs selected
identical coordinates in all eight prior cases.
Mean error moved from 4.1236 km for local Doppler to 3.9544 km with original
geometry; geometry improved four and tied four. The gain was concentrated in
339af; two 53ce changes were only 24 m and 7 m in radial error despite a 0.5 km
grid. This already-unblinded local-grid diagnostic was useful development
evidence, not prospective confirmation. Reversal improved three, worsened
three, and tied two, weakening a clean physical-orientation explanation.
Sources: [local-grid report](sources/2026_09_27_roof_balanced_confirmation/LOCAL_GRID_RESULTS.md)
and [local-grid distances](sources/2026_09_27_roof_balanced_confirmation/local-grid-distances.json).

## 4. Better calibrated reception models failed the geographic test

Calibration was made internally consistent by reconstructing candidate-specific
directions under the robust frequency model. Only 59/344 tracks had top weight
below .99, so mixture behavior was expected to affect a minority of ambiguous
tracks. A candidate-mixture reception model passed conditional six-fold
calibration gates, but its fixed-grid geography worsened: combined mean error
4.4531 km versus 4.1236 Doppler and 3.9544 original geometry. It improved two,
worsened four, and tied two. Four regressions were caused by reception evidence
overcoming a slightly better Doppler score. Predicting reception at known sites
therefore did not imply useful local spatial curvature. Sources:
`reports/2026_09_27_roof_balanced_confirmation/MIXTURE_CALIBRATION_RESULTS.md`
and `MIXTURE_GEOMETRY_RESULTS.md`.

Track diagnostics showed large identity-odds reversals: in selected regression
tracks, reception could overcome frequency log odds by tens of nats. This
distinguished association discrimination from local geometry but did not prove
the reception-selected ID was correct. Source:
`reports/2026_09_27_roof_balanced_confirmation/RECEPTION_IDENTITY_OVERRIDE_RESULTS.md`.

The later dual-track diagnostic sharpened that conclusion. In 339af, 62/64
tracks retained their joint MAP identity between compared positions, and the
two switching tracks actually opposed the selected move. In the 53ce
Sacramento regression all 62 joint MAP identities stayed fixed; an exact
mixture decomposition attributed the move primarily to improved frequency
likelihood at the RX-supported identities, while direct detection-plus-ratio
changes slightly opposed it. Thus stable MAP labels did not mean reception was
providing direct spatial curvature: it could reweight identities and thereby
change which frequency fits dominated. This was a post-outcome mechanism
diagnostic, not evidence that those identities were physically correct. Source:
[dual-track diagnostic](sources/2026_09_27_roof_balanced_confirmation/DUAL_TRACK_DIAGNOSTIC_RESULTS.md).

Calibration residual audits found strong within-track dependence. Adjacent
identity-adjusted detection residual covariance ratios were 0.751 (M0), 0.576
(mean), and 0.660 (mixture); track residual-sum dispersion was 11.91, 8.99, and
8.67. Ratio residual-sum dispersion was 5.78 for the mixture. These diagnostics
rejected row independence as calibrated uncertainty. Sources:
`calibration_temporal_diagnostic.md` and `CALIBRATION_RATIO_DISPERSION.md`.

A shared detection random intercept passed calibration-only LOSO with full-fit
sigma 2.5619 logits. Numerically, ordinary Gauss-Hermite failed at large sigma;
mode-centered adaptive quadrature with 64/128 verification replaced it without
changing the model. Geographic mean error improved relative to the mixture
(4.3953 versus 4.4531 km) but remained 6.59% worse than Doppler and worse than
original geometry. Sources: [shared-detection geography](sources/2026_09_27_roof_balanced_confirmation/SHARED_GEOMETRY_RESULTS.md)
and [track random-intercept calibration](sources/2026_09_27_roof_balanced_confirmation/TRACK_RANDOM_INTERCEPT_RESULTS.md).

A shared ratio offset then passed calibration LOSO with tau 0.2518. The dual
geographic model repaired e76c and 53ce Reno but regressed both 339af priors.
Combined mean error was 4.1943 km: 4.57% better than detection-only, yet 1.71%
worse than Doppler and worse than original geometry in three cases, with no
improvements over original geometry. It was rejected for promotion. Sources:
[dual-shared geography](sources/2026_09_27_roof_balanced_confirmation/DUAL_SHARED_GEOMETRY_RESULTS.md)
and [ratio random-intercept calibration](sources/2026_09_27_roof_balanced_confirmation/RATIO_RANDOM_INTERCEPT_RESULTS.md).

## 5. What the RX model actually constrains

The frozen physical slopes are about 7.92 detection logits and 1.57 log-ratio
units per unit east-direction cosine. As an illustration only, at a 550 km
slant range a 1 km receiver shift would change east cosine by at most about
.0018: only .0144 logit and .00285 log-ratio per km. This is neither an observed
range bound nor a calibrated distance-uncertainty floor. Conversely, the median
top-three candidate east range is .502, large enough for about four logits or
.79 log-ratio units. Frequency priors are usually nearly one-hot, but the
minority ambiguous tracks can receive powerful RX identity evidence. This makes
the observed pattern scientifically coherent: RX is much better positioned to
change satellite association/basin choice than to provide kilometre-scale local
curvature.

Within-track centering did not erase all direction signal. Across 3,982 matched
calibration rows, the centered descriptive ratio slope was 1.868 versus the
fitted 1.570; all six sessions had positive covariance, and centered direction
explained about 36% of centered residual variation. However, centering retained
only 20% of raw east leverage (14% under objective-like weighting), and session
slopes ranged .945–3.296. Thus shared offsets remove much absolute-level
information but leave heterogeneous trajectory information. Source:
[spatial-sensitivity audit](sources/2026_09_27_roof_balanced_confirmation/RX_SPATIAL_SENSITIVITY_AUDIT.md)
and bound calibration artifacts.

## 6. Current status and decision boundary

No receiver-geometry model tested so far establishes a reliable general improvement in geographic accuracy
or resolution over Doppler alone, and no later model beats the original geometry model on
the development cohort. The consistent findings are:

1. timing nuisance improves residual fit but does not solve association;
2. candidate identity must be marginalized jointly with shared latents;
3. flexible residual models can destroy association information;
4. reception likelihood predicts reception but can overrule frequency evidence
   in geographically harmful ways;
5. repeated RX outcomes are strongly dependent;
6. calibrated shared effects repair some regressions but do not yield net
   geographic improvement; and
7. RX direction evidence is more plausibly an association cue than a fine
   position sensor at the present antenna/noise calibration.

The bounded calibration-only association-transfer diagnostic then conditioned
candidate weights on one provenance-separated RX block and predicted Doppler in
the other, in both temporal directions. All 344 tracks closed across six
shards; 32 rows fell in the fixed midpoint guard. Normal-direction
occupied-second-weighted gain was **-0.004239 NLL/observation** for early A to
late B (worse; only 2/6 sessions improved) and **+0.000359** for B to A (tiny;
3/6 improved). This mixed, direction-asymmetric result does not support RX as a
reliable association update. It is exploratory conditional calibration
evidence, not randomized grouped validation, physical identity decoding, or a
geographic test. Sources:
[association-transfer protocol](sources/2026_09_27_roof_balanced_confirmation/ASSOCIATION_TRANSFER_PROTOCOL.md)
and [association-transfer summary](sources/2026_09_27_roof_balanced_confirmation/association-transfer-summary.json).

## Artifact gaps and cautions

The persisted reports above are the authority. Independent-soft and scan-60d9
have standalone primary reports and are summarized directly here. Any earlier
discussion not represented by a persisted artifact is omitted rather than
reconstructed from memory. Historical shared-candidate-list location numbers
remain only invalid-method diagnostics; they must not be mixed into frozen
independent-prior comparisons or presented as gains. The temporal transfer
test is descriptive and exploratory, not randomized grouped validation.

## Bundled source snapshots

The following evidence accompanies this log:

- DS5: [probabilistic](sources/2026_09_26_ds5_probabilistic/REPORT.md),
  [empirical prior](sources/2026_09_26_ds5_empirical_prior/aggregate.json),
  [08:50 diagnosis](sources/2026_09_26_ds5_0850_diagnosis/REPORT.md),
  [residual polynomial](sources/2026_09_26_residual_polynomial/REPORT.md),
  [soft prototype](sources/2026_09_26_association_soft_prototype/REPORT.md),
  [independent soft](sources/2026_09_26_independent_soft/REPORT.md),
  [joint location](sources/2026_09_26_joint_location_prototype/REPORT.md),
  [joint mixture](sources/2026_09_26_joint_mixture/FULL_DS5_REPORT.md),
  [penalized joint](sources/2026_09_26_penalized_joint/REPORT.md), and
  [60d9 review](sources/2026_09_27_scan_60d9d1e77c14da0a/REPORT.md).
- Confirmation chronology: [FIRST](sources/2026_09_27_roof_geometry_confirmation/RESULTS.md),
  [depth-balanced repair](sources/2026_09_27_roof_geometry_confirmation/BALANCED_DEVELOPMENT_RESULTS.md),
  [SECOND](sources/2026_09_27_roof_balanced_confirmation/RESULTS.md), and
  [posthoc local grid](sources/2026_09_27_roof_balanced_confirmation/LOCAL_GRID_RESULTS.md).
- Roof model evidence: [mixture calibration](sources/2026_09_27_roof_balanced_confirmation/MIXTURE_CALIBRATION_RESULTS.md),
  [mixture geography](sources/2026_09_27_roof_balanced_confirmation/MIXTURE_GEOMETRY_RESULTS.md),
  [detection random intercept](sources/2026_09_27_roof_balanced_confirmation/TRACK_RANDOM_INTERCEPT_RESULTS.md),
  [shared detection geography](sources/2026_09_27_roof_balanced_confirmation/SHARED_GEOMETRY_RESULTS.md),
  [ratio random intercept](sources/2026_09_27_roof_balanced_confirmation/RATIO_RANDOM_INTERCEPT_RESULTS.md),
  [dual geography](sources/2026_09_27_roof_balanced_confirmation/DUAL_SHARED_GEOMETRY_RESULTS.md),
  [dual-track mechanism](sources/2026_09_27_roof_balanced_confirmation/DUAL_TRACK_DIAGNOSTIC_RESULTS.md),
  [temporal residual audit](sources/2026_09_27_roof_balanced_confirmation/calibration_temporal_diagnostic.md),
  [ratio dispersion](sources/2026_09_27_roof_balanced_confirmation/CALIBRATION_RATIO_DISPERSION.md), and
  [spatial-sensitivity audit](sources/2026_09_27_roof_balanced_confirmation/RX_SPATIAL_SENSITIVITY_AUDIT.md).
- Machine-readable anchors: [local grid](sources/2026_09_27_roof_balanced_confirmation/local-grid-distances.json),
  [mixture](sources/2026_09_27_roof_balanced_confirmation/mixture-geometry-distances.json),
  [shared detection](sources/2026_09_27_roof_balanced_confirmation/shared-geometry-distances.json),
  [dual shared](sources/2026_09_27_roof_balanced_confirmation/dual-shared-geometry-distances.json), and
  [association transfer](sources/2026_09_27_roof_balanced_confirmation/association-transfer-summary.json)
  with source-shard hashes retained in the summary. The six larger original
  shard files are not duplicated in this report bundle.
