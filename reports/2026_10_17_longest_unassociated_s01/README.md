# Why S01's longest unassociated track was missed

The strongest current explanation for **RX1 CH6 T001** is **STARLINK-33735,
NORAD 63474**, with an effective orbital phase near **−2.7 seconds**. This is
a fixed-known-position compatibility result, not independently authenticated
satellite identity. It explains a substantial missed family, not every remaining
unassociated curve or the geographic error.

## Which track and whether its polynomial is credible

“Longest” here means duration: 71 points from 105.269 to 177.301 seconds,
a 72.033-second span. Two other unassociated fragments have 80 points each;
RX1 CH2 T000 has the longer duration of that pair, 58.569 seconds. The main
investigation deliberately follows the 72-second curve.

The robust radio-only order comparison keeps **all 71 observations** in a
degree-4 curve at **130.8 Hz RMS**, penalized score 75.29. The degree-2 and
degree-3 alternatives score 222.87 and 254.80 and cannot explain the complete
curve as well. Removing an affine fit from the raw measurements leaves 7,372 Hz
RMS: this is actively measured curvature, not a nominal quadratic on a line.
The maximum quartic point leverage is 0.669, and five consecutive residual
blocks have RMS 124 / 147 / 118 / 158 / 100 Hz. Unlike the earlier T009 case,
the physical satellite curve also explains every original point. No endpoint
removal, order increase or measurement alteration is needed.

## Two separate causes of the miss

First, the old search constrained 63474 to **±0.616 seconds**, derived as three
times an uncalibrated successive-TLE disagreement proxy of 0.205 seconds.
The current fitted phase sat at the negative boundary. The matching phase,
−2.7 seconds, was outside that box. The original Gaussian phase penalty is
retained in this investigation; the profile range is expanded to ±15 seconds.
The selected element is approximately 20.63 hours old at the scan origin.
Successive-TLE agreement is not a calibrated error covariance and cannot prove
that a larger correction is impossible. Nor does the fitted correction prove
that orbit error is its physical cause: model discrepancy can also project onto
this parameter. It is not an inferred receiver UTC correction.

At the old phase, even allowing its required **+5,114 Hz** component constant,
outside the 3,000 Hz gate, the target has **1,556 Hz RMS**. Its residual slope
is **+86.1 Hz/s**; removing a diagnostic affine component still leaves 364 Hz
RMS. A small extra LNB drift cannot explain this within the existing ±1 Hz/s
hardware hypothesis. No such per-track slope is adopted.

Second, the earlier family test required all four current nominations to pass
together. **CH3 T002 does not follow the same curve**, so it vetoed the other
three even after widening the phase search. Being nominated to the same NORAD
at an inadequate phase does not establish common-family membership.

## Full candidate competition and curved support

All **1,707 prepared causal candidates** compete on the same **601-state
−15…+15 second grid**, with every original target point, time, RF and native
alias accounted for. Hardware stays frozen. Candidates with existing admitted
curved support retain their established phases in the admissible comparison;
linear-only matches cannot lock or rank a phase. An additional fully free phase
comparison is diagnostic only. In both c arms, **63474 is the sole passing
candidate** for the target, even in the fully free comparison.

The closest other shape competitor, 47126, reaches about 211 Hz RMS near
+13.35 seconds but fails the residual screens. Low RMS alone would leave a
misleading alternative. These statements are conditional on the prepared bank,
finite grid, fixed hardware and supplied GPS; they are not a false-discovery
probability or proof that an untested object/phase is impossible.

Radio-only RF-normalized overlap checks identify two additional curved
companions. CH2 T001 agrees with the target's shape at 114 Hz RMS over 61
overlapping points; CH7 T001 agrees at 128 Hz over 21 points. Their raw affine
residual RMS values are 2,874 and 903 Hz, respectively. Both exceed the measured
curvature threshold. No linear fragment chooses the correction.

| Curved fragment | Points | Old physical RMS | RMS at −2.7 s | Component constant | Individual gates |
|---|---:|---:|---:|---:|---|
| RX1 CH6 T001 | 71 | 1,556 Hz | **132 Hz** | −1,207 Hz | Pass |
| RX1 CH2 T001 | 61 | 1,087 Hz | **113 Hz** | −699 Hz | Pass |
| RX1 CH7 T001 | 21 | 575 Hz | **136 Hz** | −1,234 Hz | Pass |
| RX1 CH3 T002 | 27 | 2,112 Hz | 1,995 Hz | +8,011 Hz | Remains rejected |

The joint profile uses all **180 original nomination points**. The unsupported
27-point fourth member pays the existing whole-curve clutter cost; it is not
silently removed. The existing score retains component-constant priors, one
satellite phase prior, conditional phase complexity and hardware complexity.
The three supported members contain 153 points. Joint uniqueness follows from
requiring the target to pass on the exact same full-bank grid: no other candidate
passed that necessary condition. Rejected members contribute no phase-volume
information. A new regression test protects this no-veto/clutter accounting.

For each of the three supported curves, fitting the phase from the other two
selects −2.7 s and the omitted curve still passes. This is a phase-transfer
diagnostic; the final fit uses all three. It is not a holdout estimate of identity
accuracy, and the original frozen hardware fit already used this scan's curved
measurements. The distinction matters when describing independence.

![Target and family diagnosis](longest_track_diagnosis.png)

## Coverage consequence and the remaining residual limitation

After freezing that curved-derived phase, five additional short fragments can
associate. The per-fragment compatibility overlay gains **231 points** in eight
fragments in both c arms: 153 on the curved anchors and 78 on shorter fragments.
No old accepted identity or point is lost. S01 moves from **2,291 to 2,522 of
4,797 raw GLRT points: 47.76% → 52.57%**. The lossless shared-constant merger
gives 85 / 79 total groups in c=0 / fitted-c. All original Graph IDs remain
accounted for, including the explicit T009 background point. Old sealed reports
and baseline association files remain unchanged.

![Recovered family across channels and receivers](recovered_family.png)

**This is not one proven noise-white merged track.** Individual recovered
fragments pass the existing mean, slope, quadratic, step and lag-1 gates, but
pooling the 153 curved-anchor residuals reveals cross-observation correlation.
At −2.7 s the pooled step statistic is 4.08 and lag-1 correlation is 0.492;
the independent-noise reference limit is 4/sqrt(153) = 0.323. At −2.75 s the
pooled slope/step checks pass, RMS improves to 123.8 Hz, but lag-1 correlation
remains 0.476. Adding a diagnostic shared degree-4 residual correction only
reduces it to 0.444 and is not favoured by the recorded complexity comparison.
No extra polynomial correction is adopted. The underlying cause of the
correlation is not established. This prevents claiming perfectly independent
white residuals or collapsing every fragment into one clean carrier track.

The 231-point number therefore means additional **per-fragment frequency
compatibility**, under the existing gates, with an explicit pooled limitation.
The merger continues to apply member and pooled checks to each proposed
shared-constant group. Future localization must model or validate the remaining
correlation; the lower in-sample frequency error does not prove better position.

## Why many other fragments remain unassociated

Before this overlay, S01 had 68 unassociated polynomial fragments containing
2,195 points, plus 311 raw GLRT points without a retained polynomial. Of those
68 fragments, **63 / 2,094 points** have no passing candidate under the frozen
current phases. The other **5 / 101 points** pass frequency checks but lack
curved support for their satellite's nonzero phase. They are short/linear and
correctly cannot validate that phase themselves.

For the nearest current nominations, 58 fragments / 2,019 points fail a residual
structure screen, 23 / 603 exceed the constant-bias bound, and 7 / 276 exceed
the RMS bound. **These categories overlap.** They are descriptions of the saved
nomination, not proof that no alternative calibration or satellite can fit.
This investigation demonstrates one concrete failure pattern: phase clipping
combined with an all-nominees-must-belong grouping rule. It does not establish
that all other misses have the same cause.

After the overlay, 60 polynomial fragments and 2,275 raw GLRT points remain
unassociated. The next longest by duration is RX1 CH4 T001; the two largest by
point count remain RX1 CH2 T000 and RX2 CH3 T000. Their own physical diagnostics
must determine whether the same repair applies.

The algorithmic change to pursue is curved-consensus family construction with
an explicit clutter hypothesis, followed by joint phase competition and frozen
calibration for linear-track extension. A failed family member must retain its
cost and identity uncertainty without automatically vetoing coherent members.
Existing admitted curved phases and residual gates remain protected.

Seventy focused tests and changed-source Ruff checks pass. The full numerical
phase matrices, original IDs, exact point residuals, priors, source snapshots,
transfer tests and unchanged earlier input seals accompany the report.
No new collection, QNAP mutation or golden-fixture change occurred. No new blind
position estimate or sub-0.5 km result is claimed.
