# Sparse causal prediction: timing is the next discriminating obstacle

The fixed sparse-history predictor supplies an earlier-only forecast for
**453/576 development receiver cells**, versus 188/576 with a gatepassing donor
on the immediately preceding visit. Archived target compatibility shows that
many natural CH5–8 opportunities survive missing visits. It also shows a
systematic timing prediction bias: primary forecasts agree with an original
gatepassing target within 16 samples/500 Hz in 143 cells, but within two
samples/500 Hz in only ten. These are compatibility diagnostics, not new
detections, independent truth, RF qualification, or lower position error.

No raw IQ was opened or scored in this branch. Validation target files remain
unopened. The next measurement test belongs to the separately frozen timing
worker, which must account for search exposure, confirmation support, CFO
accuracy, ambiguity and false confirmations before any position propagation.

## Frozen development panel and predictor

The panel uses the twelve development recordings in the whole-recording split,
CH1/4 controls and CH5–8, counter fractions 20/40/60/80%, and both RX IDs.
Every one of the 288 paired windows has verified public source/manifest/index
metadata. Target nomination uses metadata only. Archived target candidates
reside in a separately sealed evaluation file and never enter the predictor.
The observations have prior-study exposure; this is development evidence from
one existing corpus, not new-location or unseen-data validation.

The earlier horizon is at most twelve same-channel/RX/edge processed visits
within 4.5 seconds. Original rank <=8 and margin >=0.025 define donor candidates;
near-identical aliases are coalesced by fixed rules. Chronological candidate
births, compatible extensions and missed tracks survive in a bounded beam of
eight alternatives, with at most two paths per latest donor. One-donor fallback
is explicit and receives broad rate uncertainty. Rules and uncertainty
allowances were frozen before archived-outcome analysis; no rule was tuned.

There are 3,187 retained alternatives across 453 cells. Primary mode donor counts
are 54 single-donor, 37 two-donor and 362 three-or-more-donor histories. Another
123 cells explicitly have no donor. At least one retained mode bridges a missed
visit in 451 cells. There are 6,552 alternative compatible extensions and 10,570
pruned intermediate modes under the declared cap. Those counts describe the
bounded search graph, not independent observations or validated identities.

| Channel | Cells | Latest-visit donor | Sparse forecast | Original target gatepass | Primary compatible ±16 samples /500 Hz | Any of 8 compatible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CH1 | 96 | 31 | 84 | 47 | 39 | 40 |
| CH4 | 96 | 39 | 80 | 49 | 46 | 46 |
| CH5 | 96 | 27 | 70 | 16 | 12 | 14 |
| CH6 | 96 | 33 | 73 | 16 | 13 | 13 |
| CH7 | 96 | 27 | 80 | 21 | 19 | 19 |
| CH8 | 96 | 31 | 66 | 16 | 14 | 15 |
| Total | **576** | **188** | **453** | **165** | **143** | **147** |

For CH5–8 specifically, 289/384 cells have a sparse forecast, 69 have an
original target gatepass, and 58 primary /61 any-mode cells satisfy this
archived compatibility criterion. Across all channels, 162/165 original target
gatepassing cells have some retained forecast. The panel thus discriminates
missing-history failure from a prediction/scoring problem much more effectively
than requiring three consecutive passing visits.

![Sparse donor opportunity](opportunity.png)

## Timing neighborhoods, modes and predictive widths

At a fixed 500 Hz CFO threshold, primary archived joint compatibility rises
from **10 at ±2 samples to 143 at ±16**, then 144 at ±64 and ±256. Allowing
all eight earlier-selected alternatives changes these counts to 25,147,148,148.
At ±16 samples the first 1/2/4/8 retained modes yield 143/144/146/147 compatible
cells. This separates mode ordering from timing error: the dominant difference
here comes from a small timing neighborhood rather than large mode multiplicity.

Target matching in this survey asks whether *any original passing target mode*
is compatible with a retained forecast. It is a target-chosen best-case
evaluation; it does not choose, reorder or validate the predictor's modes.
Original target outcomes supply no external identity or natural CFO truth.
Counts include all requested cells; a target without an archived gatepass
cannot be classified as a recovered signal from this metadata analysis.

![Fixed archived compatibility thresholds](timing_compatibility.png)

The declared widths are heterogeneous. Primary heuristic timing three-sigma
half widths have p05/median/p95 **5.24/14.06/844.44 samples**; CFO half widths
are **372/796/23,618 Hz**. These are engineering forecast scales, not calibrated
confidence intervals. Short bounded downstream searches can truncate broad
one-donor or long-gap predictions; they must retain that limitation explicitly.
The broad heuristic bands contain an archived target mode in 150 primary and
158 any-mode cells, but this is neither calibrated coverage nor a FAR test.

## Signed timing diagnosis and zero-rate carry control

The coordinator requested a separate posthoc diagnosis after the frozen survey.
It changes no predictor or raw-scoring policy. The cohort comprises 144 cells
with a primary mode and at least one original gatepassing target within 500 Hz.
The fixed matching policy selects the minimum absolute CFO difference, then
original rank; **timing does not select the matched target**. Both fitted and
latest-donor zero-rate timing are evaluated against that same selected target.
Signed error is target epoch minus forecast, circularly in native samples.

| Diagnostic in fixed CFO-compatible cohort | Fitted timing | Latest-donor zero-rate carry |
| --- | ---: | ---: |
| Cells | 144 | 144 |
| Median signed error (samples) | −5.58 | +11.95 |
| Median absolute error (samples) | 5.61 | 29.74 |
| Within ±2 samples | 10 | 5 |
| Within ±16 samples | 142 | 45 |

Fitted signed error has IQR **−7.09..−4.29 samples** and p05/p95
**−10.77..−1.43**. Every channel/RX stratum has a negative median, ranging
about −3.86 to −6.45 samples. The median is −4.85 for gaps below 0.5 s
(93 cells), −5.74 for 0.5–1 s (two), −8.54 for 1–2 s (48), and −23.58 for
2–4.5 s (one). Three-or-more-donor histories have median −5.63 (135 cells);
two-donor histories median −2.12 (nine). No one-donor primary enters this
posthoc CFO-compatible cohort; its real accuracy is therefore unestablished.

This is predominantly a systematic overshoot, with donor-age dependence,
rather than centered timing scatter. Linear timing-rate fitting substantially
improves zero-rate carry while leaving a reference/model/curvature question.
The source convention is tested explicitly below; no empirical bias correction
or quadratic model was fitted to these target outcomes. The data do not yet
identify a physical cause or justify a satellite-clock/Doppler interpretation.

Two errors outside ±16 remain visible: **+1473.22 samples** at
DS24-0017/CH1/F20/RX0 and **−23.58 samples** at DS24-0101/CH1/F80/RX0.
The former has CFO agreement within 68.83 Hz but a very different arrival,
demonstrating that CFO agreement does not establish identity. Its fitted
heuristic timing width is only 5.86 samples. Because this positive outlier is
large, the cohort mean error is +4.36 and RMS 122.95 samples; reporting only
the negative median would conceal the tail. The latter has a 3.54 s donor gap.

![Signed timing and carry diagnostic](signed_timing_diagnosis.png)

The signed-diagnostic within-16 count142 differs from the survey's143 because
the survey may choose a target by joint compatibility, while this diagnosis
chooses the closest CFO only. The difference is preserved rather than silently
selecting a target that improves the timing comparison. Full signed statistics
by channel/RX, donor count/gap and case appear in `timing_diagnosis.json`.

## Donor-only curvature diagnosis

A separately sealed posthoc diagnosis examines earlier donor epochs only.
Among 362 primary histories with at least three donors, 347 have negative
quadratic curvature, median −2.787 samples/s². In the existing CFO-compatible
target cohort, 129/135 histories have negative curvature; their donor-only
quadratic-minus-linear extrapolation difference has median −5.649 samples.
That is close to the observed −5.58-sample timing error without using any
target epoch in a fit. A curved timing trajectory therefore explains the sign
and scale of the linear extrapolation bias more directly than a common
origin/midpoint reference shift, which cancels for equal 20ms supports.

For 319 histories with at least four donors, fitting older donors and
predicting the latest earlier donor gives median absolute error 2.487 samples
for linear versus 0.237 for quadratic fits; within-two-sample counts are
116 versus 294. The quadratic result has two tails beyond sixteen samples.
Membership and association in the frozen history already used that last
donor, so this is a diagnostic within selected histories rather than an
independent held-out or fully causal qualification estimate. No revised
prediction or target correction is admitted from this analysis. It supports
testing a separately frozen conservative curvature model; it establishes
neither physical signal identity nor a satellite/clock mechanism.

![Earlier donor residual curvature](earlier_donor_curvature.png)

## Earlier-only RF-scaled coefficient coupling

Across all 362 primary histories with at least three donors, the empirical
positive relation `a_timing ≈ (Fs/actual RF)*CFO_slope` has median ratio 0.99465
and ratio IQR 0.928..1.045. The positive-relation median absolute residual is
0.149 samples/s², versus 5.497 for the negative relation. This central scale
match is suggestive, but Pearson correlation is only 0.295; positive-relation
RMS is 1.332 samples/s², with every outlier retained. The through-origin slope
0.942 and descriptive SE 0.0247 do not establish population precision because
histories share donors and coefficient errors are correlated.

Coefficient uncertainty is explicit. With engineering measurement floors
0.75 sample/75Hz, timing-acceleration conditional SE has median 0.991 and
p95 13.98 samples/s²; CFO-slope SE median is 31.9Hz/s. These are conditional
regression quantities, not calibrated RF uncertainties. All per-channel/RX
results and both signs remain in coupling_diagnosis.json.

The scorer's digital convention uses a positive epoch to select later samples
and removes positive CFO using negative complex rotation. Under a simple
propagation model with that orientation, increasing path delay would imply
the opposite sign. Native RF metadata is explicitly marked a mapping
`hypothesis`, so physical RF/IQ/LO/clock orientation is not proven. The observed
plus relation is not promoted as a physical law. SOURCE_CONVENTIONS.md gives
the derivation and limits. ROUND2_PROPOSAL.md therefore proposes a conservative
independently fitted quadratic, not fixed empirical RF coupling. No second
round was implemented or run here.

![Earlier-only coefficient coupling](timing_CFO_coupling.png)

## Time references, native ownership and verification

Persisted epoch denotes a frame start relative to its window origin. Timing
phase is therefore fitted and propagated at **support start**, while CFO has
the declared nominal **support midpoint** reference. Each target half has its
own start, midpoint, epoch, CFO and rate. The second half receives the timing
rate times its 10ms origin offset before its local-origin subtraction; half
CFOs receive the corresponding midpoint shift. `predictor.propagate` can also
evaluate explicit per-frame starts and CFO reference counters.

The existing scorer assumes one constant timing epoch within a half. This
ignores intra-half timing warp, up to two samples end-to-end at the declared
200samples/s association bound. A zero one-donor rate is an estimate with
broad uncertainty, not proof that the true rate is zero. CFO's midpoint is a
nominal reference convention and need not equal its exact pilot-weighted time.

The core freeze preserves tracking's `stream_generation` label. A separately
sealed, metadata-only native-ownership handoff distinguishes it from the exact
integer acquisition generation. `prediction_packets.json` preserves all frozen
numerical forecasts and enriches targets and donors with exact native support,
generation and IQ/index/source digests. All **1,395 selected donor windows**
have verified public index authority. All 576 native packet ownership checks
pass. No raw payload was read.

Five owned tests pass: known nonzero rates and correct origin/midpoint
conversion, missed visits and one-donor fallback, alias/rank/mode alternatives,
causal response redaction, and native-generation enrichment without numerical
mutation. The independent audit reproduces every forecast and checks fresh
target-response redaction on all 576 cells, source hashes, bounded modes and
native disjoint support. No failed or absent cell is silently dropped.

Immutable SHA256 handoff values:

- Core protocol: `f31f786c6231be33497faf4071c32ffb6d9f6574fabae3cb4fbba262e8fc771d`
- Metadata-only panel: `d659de987fde5b3df9b449f6a20798c2f91f24800a04a85d1ba06735c20d283a`
- Archived evaluation-only targets: `dad69273221c661613956c64c868230faa97445b83d9f593f21027e8c8a5162f`
- Earlier-only forecasts: `157cc6664b88f8fc1f2b481256b58b5c76598050fb63e7943e920d0dad7d9992`
- Enriched native packets: `ae1183913e40a37258c5bdf048459fc4cf3526928b119dfd55119bb3d17aa721`

Use repository `.venv/bin/python`, BLAS thread counts fixed to one, and the
historical public runtime path recorded in the shared plan for metadata reads.
`study.py` separates panel preparation, prediction and donor metadata authority;
`survey.py` and `timing_diagnosis.py` are evaluation only. Each numerical stage
has a580-second bound. Figures have PNG/PDF artifacts. JSON, CSV, sources,
tests, independent verification and final artifact hashes accompany this report.
No git/push, production changes, new RF, QNAP writes, golden-fixture changes,
validation-target analysis or geographic fit occurred in this branch.
