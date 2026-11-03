# Three multi-peak association prototypes on DS23-0342 and DS23-0039

All three prototypes correct the two investigated structural failures under
the common, fixed receiver calibration and RF-derived position. Scan 0342's
apparent single curve becomes two overlapping tracks. Scan 0039's fragmented
winning-mark curve becomes one continuous track with all 88 observations in
the maximum-posterior assignment. The simpler greedy graph repair matches the
joint search here and retains one more point than EM in scan 0342.

These are **three allocation/refinement variants sharing one candidate-generation
stage**, not three independently initialized full localization pipelines. The
experiment covers the requested receiver/channel intervals, not every lane of
both scans. It does not estimate a new position or demonstrate improved
position accuracy. The existing evaluation and diagnostic artifacts are read
only; runtime pipeline code and golden fixtures are unchanged.

## Scope and common evidence

| Scan and lane | Interval | Original winning GLRT marks | Canonical multi-peak observations | Causal satellites screened |
|---|---|---:|---:|---:|
| DS23-0342 RX1 CH2 | 60–140 s | 63 | 128 | 1,539 |
| DS23-0039 RX1 CH1 | 134–240 s | 88 | 128 | 1,488 |

The second interval includes the curve's beginning at 134.887 s, slightly
before the requested approximate 140 s boundary. Its final mark is at
239.373 s. No points around the scan 0342 handover or its isolated 114 s winner
are removed manually.

All gated candidates in each probe are reopened from the original public
tracking artifact. Within a probe, circular-frequency candidates within 300 Hz
of the highest-margin representative are grouped together, including replicas
separated by the 227.273 kHz alias period. Distinct resolved peaks remain
separate observations. Each canonical peak can have only one owner, but two
different peaks in a probe can belong to different satellite tracks. Each
satellite track can select at most one canonical peak from a probe.

The frequency noise is frozen at the radio-only estimate: 132.048 Hz for
0342 and 65.208 Hz for 0039. The receiver calibration comes from the previous
leave-target-out analysis: the problematic curved track in 0342 and the two
curved target fragments in 0039 are masked from calibration. Their linear
extension never supplied calibration votes. Shared receiver offsets, band
offsets, linear drifts and nonlinear receiver terms are then held fixed.

The common position is inferred from the other retained RF evidence, using
the earlier regional-center-started analysis. **Reference GPS is not used.**
This is an isolation experiment using that saved inference, rather than a
new cold start of the full 25×25 km localization search. Only causal TLE
states are used; no post-observation element sets enter the experiment.

Both `c=0` and fitted-`c` arms use identical canonical observations, the same
causal catalogue, matched nominated satellite sets, priors and numerical
budgets. The learned RF-dependent constant coefficient `c` is distinct from
the satellite Doppler-scale parameter described below.

## Shared graph and curve hypotheses

The graph searches up to 16 alternative edge chains without reserving their
points during proposal generation. Each whole path is tested with a penalized
C1 polynomial representation before observation ownership is finalized.
Systematic prefix/suffix proposals at 35%, 50% and 65% of path length offer
alternatives when a graph path changes emitter; no scan-specific handover time
is supplied. Both whole paths and supported subpaths nominate satellites.

Every causal satellite is screened using regularized phase and shape tangents.
The top three nominations per supported subpath receive nonlinear refinement
using the continuous causal state bank with exact phase-shift geometry. The
tangents are only a shortlist/initialization device. There is no hard-coded
65504, 68214, 59569 or 66478 candidate whitelist in the implementation.

Each physical hypothesis has three shared local parameters: phase, a constant
frequency bias, and a fractional multiplier on orbital Doppler. Gaussian prior
widths are respectively 3 s, 1,000 Hz and 0.005. Absolute numerical bounds are
±15 s, ±3,000 Hz and ±0.005. There is **no free per-piece linear drift** or
polynomial correction to the satellite prediction. The Doppler multiplier is
a compact diagnostic shape correction, not an established RF calibration
defect or a fitted TLE element.

Growth uses a three-radio-sigma circular-frequency gate. Accepted hypotheses
must have at least 12 probes, span at least 8 s, have no observation gap over
10 s, pass the existing mean/slope/quadratic/step/autocorrelation screens, have
orbital RMS at most three radio sigmas and no residual over six radio sigmas.
Their fitted polynomial bending after projecting out an affine line must
exceed two radio sigmas. This last gate prevents nearly linear new arcs from
calibrating their own phase/shape corrections. Such arcs may still be useful
as extensions from independently calibrated families, but that separate
linear-extension stage is outside this prototype.

Polynomial degree is at most four. The search considers up to two knots on a
5 s grid and enforces exact shared frequency and slope at each knot. It charges
coefficients and searched knots in BIC and requires at least four observations
per local polynomial coefficient. The same model/track complexity costs are
included in all allocation objectives. Passing the finite-sample residual
screen does not certify independent Gaussian noise or satellite identity.

## The three variants

1. **Greedy graph repair:** rank the admissible whole-track hypotheses by
   penalized RF evidence, accept tracks greedily and resolve individual peak
   ownership with exclusive per-probe matching. It has no global reconsideration
   of the accepted family set.
2. **Joint paths:** evaluate compatible subsets of up to four families from
   the ten best distinct nominated families. For each subset, solve peak
   allocation exactly within every probe, charging physical priors and model
   complexity. Whole-family parameters remain fixed during subset comparison;
   final allocated tracks are refitted and gated. This is bounded global
   selection within the supplied pool, not an unrestricted global flow or
   globally optimal joint orbital fit.
3. **Satellite EM:** take three ranked compatible family-set initializations.
   Each run performs 12 rounds of exact per-probe exclusive matching
   probabilities followed by weighted, Gaussian-prior-constrained shared
   phase/bias/scale fitting. The likelihood has an explicit unassigned/clutter
   option. The best family-set run is selected by penalized RF likelihood.
   Point assignments and parameters change during EM; catalogue nomination
   is not repeated within each iteration, and the family set is fixed within
   each run. Thus this is a bounded conditional EM prototype, not full
   satellite-birth/location EM.

The EM output includes both its most likely exclusive assignment (**MAP**) and
a conservative subset requiring conditional assignment posterior ≥0.8. These
posterior values depend on the supplied candidate family set, noise and peak
evidence model; they are not calibrated identity confidence probabilities.
The association figures use MAP so all three methods have comparable gates.
The remaining-evidence figures show the conservative EM subset and flag its
ambiguous points separately.

## Results

Counts below are for `c=0`. Fitted-`c` gives the **same counts in every row**.
“Secondary” means a distinct canonical peak that was not the original
one-winner-per-probe observation, not a second count of an alias replica.

| Scan | Method | Accepted tracks | Original winners associated | Winner percentage | Additional secondary peaks | Total peaks |
|---|---|---:|---:|---:|---:|---:|
| 0342 | Original pipeline in this interval | — | 2 / 63 | 3.17% | Not considered | 2 |
| 0342 | Greedy graph repair | 2 | 53 / 63 | **84.13%** | 25 | **78** |
| 0342 | Joint paths | 2 | 53 / 63 | **84.13%** | 25 | **78** |
| 0342 | EM, MAP | 2 | 52 / 63 | 82.54% | 25 | 77 |
| 0342 | EM, posterior ≥0.8 | 2 | 50 / 63 | 79.37% | 24 | 74 |
| 0039 | Original pipeline in this interval | 3 fragments | 66 / 88 | 75.00% | Not considered | 66 |
| 0039 | Greedy graph repair | 2* | 88 / 88 | **100.00%** | 26 | **114** |
| 0039 | Joint paths | 2* | 88 / 88 | **100.00%** | 26 | **114** |
| 0039 | EM, MAP | 2* | 88 / 88 | **100.00%** | 26 | **114** |
| 0039 | EM, posterior ≥0.8 | 2* | 85 / 88 | 96.59% | 26 | 111 |

*Scan 0039 has **one** track for the requested 88-point winning-mark curve.
The other track is a separate secondary-peak curve conditionally associated
with 66478, not another fragment of the requested curve. Its decoded identity
has not been established independently.*

Do not divide total peaks by original winning probes: two physical signals
can occur in one probe. Against all 128 canonical observations, the greedy
graph/joint allocation rates are 60.94% for 0342 and 89.06% for 0039. This
denominator includes clutter and unresolved candidate evidence and is different
from the original one-winner denominator.

![Association count comparison](comparison.png)

### Scan 0342: the false bridge is separated

![All three methods, associated curves and satellite residuals](DS23-0342_c0.png)

| Method | Satellite hypothesis | Points | Orbital RMS | Polynomial representation |
|---|---:|---:|---:|---|
| Greedy / joint | 65504 | 42 | 119.3 Hz | One cubic |
| Greedy / joint | 68214 | 36 | 121.5 Hz | One quartic |
| EM MAP | 65504 | 43 | 120.1 Hz | One cubic |
| EM MAP | 68214 | 34 | 98.7 Hz | One cubic |
| EM ≥0.8 | 65504 | 40 | 120.5 Hz | One cubic |
| EM ≥0.8 | 68214 | 34 | 98.7 Hz | One cubic |

The earlier curve continues through secondary peaks while the later curve
becomes the winner. No method accepts the original winner-switching sequence
as one satellite track. Some ambiguous near-crossing peaks receive different
owners in EM, but the two-curve structure remains intact.

The original rejected T002 contained 48 winning observations. Greedy and
joint recovery associate **46/48**; MAP EM associates **45/48**, and conservative
EM associates **44/48**. The two common remaining original points are at
83.020 and 117.639 s. Against the final greedy/joint models, their nearest
residuals are −467.4 and −524.3 Hz, exceeding the 396.1 Hz association gate.
They are retained as unassociated evidence rather than silently trimmed from
the input. A larger gate could admit them, but was not tuned to force a full
48/48 result. The other unassociated winners in the 60–140 s interval include
short surrounding fragments for which these prototypes do not obtain a
supported new curved calibration.

![Remaining points and conservative EM ambiguity](DS23-0342_c0_unassociated.png)

The associated plots subtract one common display-only affine line from all
curves and measurements, aligning integer alias gauges for readability. They
zoom to accepted curves; remaining-evidence plots show the full circular
frequency range. The plotting transforms do not enter fitting.

### Scan 0039: one continuous 88-point track

![All methods recover the continuous winning-mark curve](DS23-0039_c0.png)

The requested winning-mark curve is associated with 59569 from 134.887 to
239.373 s. Every MAP variant includes all 88 winners, replacing three
interleaved fragments with one track and recovering the **22 previously
untracked winning points**. It uses two quartic pieces joined continuously in
frequency and slope at 180 s. Polynomial RMS is 58.9 Hz; the orbital
phase/bias/scale model has 71.7 Hz RMS.

The 26-point secondary curve at 190.690–219.247 s is consistent with 66478
under the same conditional model, with 51.4 Hz RMS in the `c=0` arm. It is a
separate curve and does not account for any original winning marks. This
additional association is useful RF evidence, but should not be confused with
an independently confirmed satellite identity.

At posterior ≥0.8, EM retains 85 of the 88 primary points in the same continuous
track. Its lower 65.1 Hz RMS is on a smaller selected set; it is **not** evidence
that EM fits the full curve better than the 71.7 Hz MAP result.

![Remaining points for each method](DS23-0039_c0_unassociated.png)

## Safeguards and an explicit ablation

Distinct satellite hypotheses often explain the **same** observed curve. They
must compete as alternative identities rather than become additional emitters.
Joint search therefore excludes simultaneous family hypotheses that share
more than 60% of the smaller hypothesis's canonical peaks. Real resolved
crossing curves mainly use different peaks and remain compatible. Conflict
pairs are unchanged between 40% and 60% on both scans/arms. A weaker 80% rule
admits an additional overlapping alternative in 0342; 0039's conflict set is
unchanged. This threshold is a prototype heuristic, and its transfer to other
scans remains unvalidated. The complete conflict sets are recorded in
`validation.json`; no broad threshold-insensitivity claim is made.

The guard is evaluated together with polynomial/parameter complexity and the
active-curvature requirement. A separate run removes only the identity guard
with the same observations, nominations, priors and search budgets:

| Scan / allocation | Guard on | Guard off | Interpretation |
|---|---:|---:|---|
| 0342 joint, total associated peaks | 78 in 2 tracks | 85 in 3 tracks | Extra hypothesis partitions an already explained curve |
| 0342 conservative EM, total associated peaks | 74 in 2 tracks | 34 in 1 accepted track | Competing duplicate models damage assignment/gating |
| 0039 joint, total associated peaks | 114 | 114 | Complexity already prefers the simpler family set |
| 0039 conservative EM, total associated peaks | 111 | 111 | Same accepted family set under this budget |

The larger unguarded association count in 0342 is **not treated as a gain**.
The goal is to explain distinct observations with coherent tracks, not maximize
counts by giving additional satellite models permission to divide one curve's
residual. Alternative identities can still be retained for review without
being counted as simultaneous tracks.

## Runtime and recommendation

Measured host times below exclude acquisition, GLRT computation, fresh TLE
propagation and the already cached receiver/position calibration. These are
single-thread numerical jobs on the development host; some jobs ran concurrently.
They are not embedded benchmarks.

| Stage | 0342 | 0039 |
|---|---:|---:|
| Common graph / catalogue / curve proposal stage | 1.19 s | 3.38 s |
| Greedy allocation and final checks | 0.014 s | 0.031 s |
| Joint allocation and final checks | 0.020 s | 0.033 s |
| Three-start EM, including MAP and conservative checks | 0.392 s | 0.323 s |

**Recommend the greedy graph repair as the immediate implementation candidate.**
It resolves both failures, retains the most supported points here and has the
least selection overhead. Keep the joint solver as a bounded ambiguity resolver:
these windows are too simple to show a recovery advantage, but its owned test
demonstrates a case where it correctly overturns greedy ownership. EM is useful
for conditional ambiguity and shared correction refinement; it does not
improve association coverage on these two intervals and costs more.

Before adopting any of these in the full localizer, rerun candidate discovery,
association and position estimation together from the regional box. Local
satellite corrections can absorb geometry error. This fixed-position experiment
cannot establish whether they preserve or improve localization information.
It also does not yet add the stage that associates nearly linear fragments
using independent family calibrations.

## Artifacts, tests and reproduction

- `comparison.csv`: paired-arm counts, denominators, target recovery and timing.
- `track_details.csv`: per-track support, RMS, polynomial order/knots and corrections.
- `DS23-*_c0.json` / `*_fitted_c.json`: input candidates, hypotheses, nomination
  attempts, all allocations, EM histories, and both EM reporting thresholds.
- `*_duplicate_ablation.json`: controlled runs without the identity guard.
- `*_remaining_winner_audit.json`: every remaining winner and its frequency
  residuals to the retained models.
- `validation.json`: allocation, residual, curvature, EM monotonicity and matched
  input audits, threshold conflict sets, plus input/source hashes.

Fitted-`c` figures are also retained:

![0342 fitted-c comparison](DS23-0342_fitted_c.png)
![0039 fitted-c comparison](DS23-0039_fitted_c.png)

The numerical component is `src/leo/analysis/research/visible_arc_variants.py`;
it imports no storage, PostgreSQL or HTTP adapters. The composition and reporting
tools are `tools/evaluate_ds23_arc_variants.py` and
`tools/summarize_ds23_arc_variants.py`.

**11 new owned tests pass; 60 tests pass in the full targeted regression selection.**
They cover alias deduplication, C1 complexity, real-step rejection, exclusive
matching probabilities, ambiguity, duplicate identities, a greedy-versus-joint
counterexample, zero-weight clutter, and monotone EM refinement. All accepted
real-data allocations are independently audited for unique ownership, one
peak per probe per track, observation gaps, residual gates and active bending.
Ruff checks pass. No science fixture was changed.

From the repository root, prefix the commands below with
`PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python`:

```sh
tools/evaluate_ds23_arc_variants.py --case DS23-0342 --arm c0
tools/evaluate_ds23_arc_variants.py --case DS23-0342 --arm fitted_c
tools/evaluate_ds23_arc_variants.py --case DS23-0039 --arm c0
tools/evaluate_ds23_arc_variants.py --case DS23-0039 --arm fitted_c
```

Repeat those four commands with `--allow-duplicate-models` for the controlled
ablation, then run `tools/summarize_ds23_arc_variants.py` to regenerate tables,
figures and numerical audits. Calibration-cache provenance is included in the
hashes; no external services are needed for these frozen-data replays.
