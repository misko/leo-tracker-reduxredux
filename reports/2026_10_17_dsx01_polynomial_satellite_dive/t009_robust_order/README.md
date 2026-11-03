# T009: an isolated endpoint was driving polynomial degree

The user identified the final RX1/CH1/T009 point as potentially belonging to a
different curve. A data-only robust comparison supports that interpretation
under the existing 150 Hz noise scale. The preferred model is a quadratic on
26 points, with the final observation retained explicitly as unassociated.
No satellite, receiver calibration or position enters this partition decision.

![Polynomial repair](polynomial_comparison.png)

The final point occurs at 168.919 seconds, following an 8.166-second gap. The
median adjacent gap is 0.886 seconds. Its CFO is +9.451 kHz from the quadratic's
extrapolation. The dotted segment is a prediction across a gap, not measured
support or proof that the same carrier continued there.

## Why the old residual test missed it

| Ordinary least-squares degree | All 27-point RMS, Hz | Endpoint residual, Hz |
|---|---:|---:|
| 1 | 1,150.9 | +4,706 |
| 2 | 1,002.7 | +2,836 |
| 3 | 431.9 | +557 |
| 4 | 189.2 | +70 |

If every point must belong, higher order buys a large reduction in squared
error. The usual parameter penalty alone does not stop the isolated endpoint
from driving that reduction. The quartic endpoint leverage is 0.993. Removing
that observation for an influence calculation changes its prediction by about
10.08 kHz, despite its small 70 Hz fitted residual. This is a diagnostic of
fragile support, not a held-out evaluation of a fixed membership rule.

## Implemented robust order comparison

The new research component fits degrees 1–4 with a Gaussian/reference-clutter
contrast. Every original point contributes to every model's final score,
including a cost for a point assigned to clutter. The degree penalty is
`(degree + 1) * log(27)`. Defaults are 150 Hz noise, 2% clutter probability and
a fixed reference clutter width of 227.273 kHz. Original unwrapped alias branches
are fixed. This is a declared contrast score, not an identity probability.

EM candidates start from all observations and every leave-one-out initialization.
Every subsequent weighted fit and final score includes all 27 observations.
There is no random or interval holdout in the final fit. The estimator returns
full-length responsibilities and residuals; no input observation is deleted.

| Robust degree | Assigned curve points | Curve RMS, Hz | Penalized score, lower is better |
|---|---:|---:|---:|
| 1 | 21 | 201.8 | 168.12 |
| 2 | 26 | 115.4 | **45.86** |
| 3 | 26 | 103.5 | 46.14 |
| 4 | 26 | 100.0 | 48.63 |

The quadratic and cubic are nearly tied. The stronger finding is that the
preferred degree-2, degree-3 and degree-4 robust fits all leave the same final
point unassociated. Their small RMS differences should not be read as strong
evidence for a particular higher degree. The quadratic remains visibly curved;
the first 26 raw points have 411 Hz RMS after an affine fit over 26.26 seconds,
so their calibration eligibility does not rest on the polynomial degree label.

Sensitivity is explicit in `sensitivity.json`: at 100 Hz noise the cubic wins;
at 150 Hz the quadratic wins for all tested clutter probabilities (0.5%, 2%, 5%).
Of nine combinations across 100/150/200 Hz and those probabilities, eight reject
the endpoint. At 200 Hz with only 0.5% clutter, the ordinary quartic with all
27 points wins. This is not a universally calibrated outlier rule. Leverage and
support diagnostics should remain visible in any broader deployment.

## Effect on satellite matching

We compare the original 27-point curve and the repaired 26-point curve plus one
explicit clutter observation at the supplied fixed GPS. Both c arms use the same
partition, 1,707 candidates, original point denominator, priors and 51 phase
vectors: 49 bounded absolute grids plus the two frozen phase vectors. Hardware
is frozen. Phases for satellites already supported by accepted curved tracks
are frozen. A new phase may be profiled only from the measured-curved core.

The research cost includes the constant prior/volume term, phase prior and
conditional phase-volume term. The repaired model also pays an explicit clutter
cost for the retained point and a `log(27)` partition penalty. All residual,
visibility and 3,000 Hz constant bounds remain unchanged. Candidates are ranked
after all gates, avoiding the select-first-then-reject failure mode.

| Model | Curve / clutter points | Passing candidates c=0 | Passing candidates fitted-c |
|---|---|---|---|
| Original curve | 27 / 0 | None | None |
| Robust repair | 26 / 1 | **67920** | **67920** |

The selected phase is -1.553 seconds, within the ±5.325-second prior bound.
The component constant is -1,138 Hz for c=0 and -1,328 Hz for fitted-c. Both
have 116.4 Hz RMS and pass the existing residual screens. This candidate is
not authenticated; the phase is learned from this single repaired curved track.

![Repaired physical match](satellite_repaired_curve.png)

An incremental compatibility overlay adds these 26 previously unassociated IDs
while freezing all existing assignments. No existing accepted fragment uses
NORAD 67920, so its new phase changes no existing label's prediction. The
proposal moves each arm from 1,975 to 2,001 associated points. The original
catalogue, published analyses and baseline assignments remain unchanged; this
is a research overlay with all original IDs and the endpoint accounted for.
No geographic search or position improvement is claimed.

## The endpoint has a supported measurement

The earlier response-only pilot check independently supports its CFO, with
reported frequency uncertainty 22 Hz. Its qualified CFO differs by only -43.8 Hz
from the original CFO in the same native branch, far smaller than the 9.45 kHz
curve discrepancy. This supports retaining the measurement while questioning
its membership in this curve. It does not establish which satellite or carrier
produced the observation.

Replaying qualified measurements on the unchanged 26 core IDs, with hardware,
phase and candidate fixed and only the constant reprofiled, gives 144.0 Hz RMS
and +1.26 Hz/s residual slope in both arms. The original core has 116.4 Hz RMS
and +3.69 Hz/s slope. Both pass the noise screens. No points or weights are
silently discarded, and qualification used no satellite or position.

## Validation and remaining scope

Twenty-six focused tests passed across robust order selection, component bias,
phase geometry, residual gates and lossless measurement replay. Tests include
the isolated endpoint, a genuinely supported quartic that must be retained,
alias-branch translation invariance, full-length point accounting and parameter
penalties. The real-data overlay verifies unique IDs, 26 new IDs disjoint from
existing associations, the retained endpoint and no existing user of the new
satellite phase. Figure, sensitivity, candidate grid and point records are
included here; code snapshots and hash lineage accompany the results.

The immediate next step is to check for this same failure pattern elsewhere
before broader reassociation. This one-track result does not establish false
association rates, performance across DS22 or the 0.5 km localization goal.
