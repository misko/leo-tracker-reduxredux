# DS23 visible-curve investigation: scan 0342 CH2 and scan 0039 CH1

The two intervals fail for different reasons. **Scan 0342 switches between two
simultaneously observable curves when the input keeps only the strongest GLRT
candidate per probe. Scan 0039 contains one recoverable continuous curve that
the polynomial finalization fragments after successful graph discovery.**

These are targeted diagnostics on the existing recordings. The original
evaluation inputs and results remain unchanged. No new recording, future TLE,
reference GPS position, satellite whitelist for the original acquisition, or
location-dependent correction was used. Satellite-specific follow-up tests
explicitly examine candidates nominated by the previous causal catalogue
search; they are not a new exhaustive orbital-parameter search of every
satellite. The repair is a research prototype, not a deployed pipeline change.

## 1. Scan 0342: two curves hidden by one-winner acquisition reduction

Requested interval: RX1 CH2, approximately 60–140 s. Actual RF: 10.960 GHz.

The central rejected graph track is
`DS23-0342-RX1-CH2-T002-RF10960000000.000000`, with 48 points spanning
73.582–133.486 s. Its fourth-order polynomial RMS is 157.9 Hz, which explains
why a graph and polynomial-only view makes it look convincing. A flexible
polynomial can follow a change between two nearby curves without leaving a
large residual on its selected support.

The wider requested interval also contains a different accepted track ending
at 63.275 s and another fragment beginning at 135.180 s. They should not be
silently concatenated with the central curve. The most informative extension
of the central curve begins at 65.280 s.

### Direct evidence from candidate peaks

The public tracking artifact stores multiple GLRT candidates per probe. The
track input reduces these to the single gated candidate with the largest
fractional margin. Reopening the candidate list reveals both branches in the
**same probes** after the apparent switch.

![Two simultaneous curves and the original winning points](DS23-0342_c0_peak_overlap.png)

The top panel subtracts the same straight line from every measurement and
prediction to make their separation visible; it does not change relative
frequency or remove an independently fitted slope from either curve. Black
circles identify winning marks passed to the original graph. Coloured points
are other stored, gated candidates near the two predictions, after placing
aliases on the same branch. The shaded interval is the continuation check.

At **105.082567 s**, for example, one original probe contains:

| Candidate CFO | Fractional margin | Role |
|---|---:|---|
| −614,314.6 Hz | 0.6563 | Winning peak; later curve |
| −604,688.1 Hz | 0.5852 | Secondary peak; continuation of earlier curve |

The exact original candidate records are in `tracking.json`; candidate lists
also contain near-duplicates and integer-alias replicas. The analysis does not
count those as independent emitters. The two relevant frequencies here differ
by approximately **9.63 kHz**, whereas the integer alias spacing is
227.273 kHz. Their GLRT epoch candidates also differ (3,830 versus 3,017 samples).
Another nearby candidate at −604,901.9 Hz has a smaller residual
to the fitted earlier prediction and is selected by the reporting gate; this
choice is recorded explicitly in `DS23-0342_c0_peak_overlap.json`.

There are **24 same-probe observations supporting both separated branches**
from 89.448 to 117.358 s. Predicted separation grows from 2.405 to 14.080 kHz.
The original winner generally follows the earlier branch before approximately
86 s and the later branch after 89 s; it briefly switches back near 114 s.
The second curve is therefore not simply a hypothetical extrapolation across
an empty gap.

### Satellite explanations and independent support

The earlier branch is consistent with **NORAD 65504**. The existing accepted
RX1 CH3 track covers 45.756–85.568 s with 37 points, and RX1 CH1 has another
14-point associated fragment at 47.387–59.178 s. This supplies evidence outside
the rejected CH2 track.

The receiver calibration used below is fitted with the rejected central CH2
track excluded. A Gaussian constant frequency bias is profiled for each tested
fragment, with 1,000 Hz prior width. The local phase is bounded to ±15 s, with
3 s Gaussian prior for the phase-grid comparison. Such a fragment constant
must not be interpreted as an additional learned receiver offset.

| Segment / test | Points | c=0 RMS | Fitted-c RMS | Residual screen |
|---|---:|---:|---:|---|
| 65504, 65.280–85.875 s, locally profiled phase | 20 | 162.1 Hz | 162.0 Hz | Pass |
| Same prefix, phase from other retained family evidence | 20 | 173.4 Hz | 173.4 Hz | Pass |
| 68214, 89.448–133.486 s, locally profiled phase | 36 | 145.7 Hz | 145.5 Hz | Pass |
| 65504 continuation candidate support, 89–117.7 s | 24 | 184.7 Hz | 184.9 Hz | Conditional support; see below |

For c=0, the independently calibrated family phase is −1.793 s; the phase-grid
test uses its nearest grid value, −1.750 s. Its prefix bias is +514.6 Hz,
slope statistic 2.040, quadratic BIC gain −2.364 and lag-one correlation 0.305.
The locally fitted prefix phase is −1.500 s. The suffix phase is −1.250 s
and its bias is −744.6 Hz, with slope statistic 0.123 and lag-one correlation
0.242. Neither prefix nor suffix needs a free linear frequency drift here.

The later candidate support for 65504 is particularly useful: its prediction
was fitted to the earlier 20 points, and was **not refitted to the later
candidate peaks**. Their mean residual is +36.3 Hz. However, those peaks were
selected within 600 Hz of the prediction, so 184.7 Hz is a *conditional support
RMS*, not an unbiased forecast error or formal identity probability. Near the
curve crossing, peaks within the same prediction windows cannot independently
establish two emitters; the simultaneous count requires separation >1,500 Hz.

![Prefix, suffix and polynomial comparison](DS23-0342_c0_transition.png)

Compared with the previous investigation, extending the prefix from 12 points
over 9.4 s to **20 points over 20.6 s**, checking its independently learned
phase, and finding its secondary-peak continuation substantially strengthens
the 65504 interpretation. The physical identity remains an inference from
orbital and cross-channel consistency, rather than decoded satellite identity.

### Could one satellite explain the entire central curve?

This follow-up tested actual SGP4 propagation rather than only a phase tangent.
It varied phase, mean motion, inclination, RAAN, and both eccentricity-vector
components; additional sensitivity fits allowed a linear frequency term and a
fractional Doppler scale. Candidates examined were 68214, 68004, 45096 and
65504, motivated by the previous all-causal-catalogue searches and the
cross-channel evidence.

![Single-satellite physical fit attempts](DS23-0342_c0_orbits.png)

On **53 retained winning marks** from 73.582–133.486 s, including marks
omitted by the original polynomial but excluding the isolated competing winner
at 113.983 s, the 68214 phase-plus-bias fit leaves approximately 1,427 Hz RMS.
Seven-parameter physical fits improve it to about 724 Hz with priors or 706 Hz
without priors. Even a much looser sensitivity fit allowing extra drift and
scale leaves about 553 Hz and strongly correlated residuals. Some solutions
reach implausible prior excursions or the generous numerical bounds; they are
not acceptable calibrations. Other tested candidates also retain strong
residual structure. Exact values, all parameter vectors and the matched c
arms are stored in the orbit JSON files.

This finite multistart search is not proof against every possible orbit or
every catalogue candidate. The **simultaneous secondary peaks** provide the
stronger explanation: the winning-mark curve changes between two coexisting
signals. Widening TLE priors or adding an arbitrary polynomial correction to
one satellite would conceal that data-association problem.

### Recommended correction for 0342

Preserve multiple gated candidates per probe through graph discovery. First
deduplicate numerical near-replicas and alias equivalents, then allow distinct
frequency paths to compete globally. A probe can contain evidence for two
signals; it must not force a single winner across all satellite hypotheses.
The current graph's exclusive ownership and emission model would need an
explicit candidate/alias identity rule before using this in a production
localizer. Calibrate only from supported curved families, then extend them to
secondary candidate peaks without granting those peaks arbitrary new drift
parameters. Satellite consistency should reject a false bridge before it
contributes to position fitting.

## 2. Scan 0039: successful graph discovery, failed polynomial compression

Requested interval: RX1 CH1, approximately 140–240 s. The investigated whole
curve starts at 134.887 s and ends at 239.373 s. Actual RF: 10.940 GHz.

![Original fragmented ownership and repaired single track](DS23-0039_repair.png)

The original output contains:

| Fragment | Time support | Points | Polynomial degree |
|---|---|---:|---:|
| T000 | 134.887–194.743 s | 30 | 4 |
| T001 | 195.143–208.988 s | 8 | 1 |
| T002 | 169.499–220.893 s | 28 | 3 |
| Untracked winning marks within the full interval | Interleaved and after 220.893 s | 22 | — |

T000 and T002 overlap in time and take interleaved observations from the same
visible curve. All three existing fragments are already associated with
**NORAD 59569**. The missing tail does not require a new satellite identity.

### Exact code path causing the fragmentation

Instrumentation of the unchanged graph code shows its first extracted path
has **72 observations spanning the entire 134.887–239.373 s interval**. Thus
neither the graph's maximum gap nor failure to discover the long path is the
primary cause.

`graph_tracklets._path_models` initially tries a single polynomial. Its bounded
refinement removes points outside the frequency gate before a satisfactory
whole-path piecewise representation is constructed. Recursive child paths
then grow overlapping polynomial supports. For the first full path, the
returned proposals include 74-point and multiple 62–65-point overlapping
supports. `tracklet_fitting.finish_lane` arbitrates each observation to the
proposal with the smaller residual, then refits the reduced memberships.
This leaves the three interleaved fragments and loses the continuation.

The later `_repair_structured` pass does not rescue the braid: it considers a
pair only when at least one member has residual structure. Each surviving
fragment can individually look smooth even though their union is one track.
Also, the graph finalizer omits the adjacent-fragment joining loop present in
the original polynomial fitter. Simply enabling adjacent joins would not fix
the main T000/T002 overlap; their memberships must be reconsidered jointly.
The full trace is in `DS23-0039_graph_trace.json`.

### Tested radio-only repair

The prototype fits a penalized, continuous piecewise polynomial to the
*original discovered graph path before clipping it into independently owned
fragments*. It then grows this path using the existing circular frequency
gate. It uses neither satellite IDs nor location.

The basis has polynomial degree at most four, with exact continuity of both
frequency and first derivative at each knot. Candidate knots lie on a 5 s
grid; the search permits zero, one or two knots and charges both polynomial
coefficients and searched knot locations in BIC. Each interval requires at
least eight observations and at least four observations per local polynomial
coefficient. There is no free discontinuity at a knot.

| Representation on the same 88 observations | RMS | Maximum residual | BIC, radio σ=65.2 Hz | Screen |
|---|---:|---:|---:|---|
| One quartic | 248.4 Hz | 648.2 Hz | 1,299.3 | Fail; lag-one correlation 0.871 |
| Two C1 quartics, knot at 180 s | **58.9 Hz** | **148.6 Hz** | **112.2** | Pass; lag-one correlation 0.156 |
| Three C1 quartics, knots at 180/215 s | 53.3 Hz | 111.8 Hz | 116.9 | Pass, but extra complexity loses |

The winning two-piece representation has eight polynomial coefficients, plus
one searched knot charged in BIC. The graph-path repair itself retains the
frozen 150 Hz discovery noise and 450 Hz gate; the table additionally evaluates
all representations on the same radio-estimated 65.2 Hz noise scale. The
recovered 148.6 Hz maximum is comfortably inside either three-sigma gate.

Result: **one track with all 88 observations**, replacing three fragments with
66 observations and recovering **22 previously untracked marks**. Maximum
observed sampling gap is 4.276 s. This is a repair of this radio curve, not a
claim that all scan-wide associations or localization have been rerun.

### Physical satellite check and a parsimonious alternative

With the original T000/T002 calibration contributions removed, the full
88-point curve was fitted against causal 59569 SGP4 predictions. Receiver
offsets, drifts and nonlinear smooth terms remain frozen from other retained
evidence. The target's new parameters do not recalibrate the receiver.

| Whole-curve model | Parameters fitted locally | c=0 RMS | Fitted-c RMS | Screen |
|---|---:|---:|---:|---|
| Phase and constant bias | 2 | 101.5 Hz | 104.5 Hz | Fail |
| Also a Gaussian-constrained linear term | 3 | 75.3 Hz | 75.7 Hz | Fail, marginal autocorrelation |
| Also a Gaussian-constrained Doppler scale | **3** | **71.7 Hz** | **71.7 Hz** | **Pass** |
| Phase, bias and five constrained orbital corrections | 7 | 72.1 Hz | 72.2 Hz | Pass |

The scale correction is +0.1044% for c=0 and +0.1104% for fitted-c. It multiplies
the **orbital Doppler prediction**, not the measured CFO and not the learned
RF-dependent constant coefficient `c`. Its Gaussian prior width in this
sensitivity test is 0.5%. It is a more parsimonious frequency-shape fit here
than freeing five orbital elements. A single arc cannot distinguish an
effective Doppler-scale error from correlated orbital/geometry errors; this
does not establish an RF carrier calibration defect. It should be tested as
a shared physical parameter across supporting lanes before adoption.

For comparison, the c=0 constrained orbital fit adjusts mean motion by
+0.000560 rev/day, inclination by −0.00240°, RAAN by −0.000014°, and eccentricity
vector components by +0.0000168/+0.0000408, with phase −1.869 s. Generic Gaussian
scales were 3 s, 0.002 rev/day, 0.02°/0.02°, 0.0001/0.0001, and 1,000 Hz for
phase, elements and bias. These are diagnostic priors, not independently
calibrated uncertainty estimates.

## 3. Validation, scope and reproduction

All physical fits use the same latest causal element catalogue and the same
observations and numerical budgets in the c=0 and fitted-c arms. Receiver
calibration is obtained from a five-round phase-refreshed fit using genuine
earlier causal TLE epochs; the target curved tracks are masked from its loss.
Existing nuisance design/support is preserved. Each arm begins at the same
regional center used by the original analysis. No reference GPS enters these
fits, candidate-peak selection, polynomial construction or BIC selection.

Frequency improvements here do **not** demonstrate better position accuracy.
The new repaired track and additional candidate peaks have not been used in
a new all-scan localization run. Original position-error results therefore
remain the published baseline, not a claimed outcome of this prototype.

The residual screen checks mean, slope, quadratic gain, step and lag-one
correlation. Passing it is a useful gate, not proof of independent Gaussian
noise or a calibrated satellite identity probability. The later candidate
support is explicitly prediction-gated. Numerical orbital searches are
bounded local multistart fits, not global orbit recovery.

Implementation: `tools/investigate_ds23_visible_arcs.py`.
Owned tests: `tests/analysis/test_ds23_visible_arc_tool.py`. The five tests cover
C1 continuity, BIC preference for a noisy line, alias-aware graph-path growth,
rejection of a real frequency step, and exact zero-perturbation SGP4 agreement.
Together with the unchanged graph test suite: **10 passed**. The broader
targeted regression selection also passes; see `validation.json`. Ruff checks pass.
Input and tool hashes are recorded in `validation.json`.

Run from the repository root with `PYTHONPATH=src:tools`,
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` and `.venv/bin/python`:

```sh
tools/investigate_ds23_visible_arcs.py --stage radio
tools/investigate_ds23_visible_arcs.py --stage graph
tools/investigate_ds23_visible_arcs.py --stage orbit --case DS23-0342 --arm c0
tools/investigate_ds23_visible_arcs.py --stage orbit --case DS23-0342 --arm fitted_c
tools/investigate_ds23_visible_arcs.py --stage orbit --case DS23-0039 --arm c0
tools/investigate_ds23_visible_arcs.py --stage orbit --case DS23-0039 --arm fitted_c
tools/investigate_ds23_visible_arcs.py --stage transition --arm c0
tools/investigate_ds23_visible_arcs.py --stage transition --arm fitted_c
tools/investigate_ds23_visible_arcs.py --stage peaks --arm c0
tools/investigate_ds23_visible_arcs.py --stage peaks --arm fitted_c
tools/investigate_ds23_visible_arcs.py --stage figures
```

Frozen calibration files cache expensive work and are included for auditing.
The report's figures and tables are built from the accompanying JSON artifacts.
No changes to golden scientific fixtures or existing runtime components are
required by this diagnostic prototype.
