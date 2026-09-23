# Geometric phase lost to per-dwell receiver calibration

For the two frozen candidate/location solutions from the
[random phase comparison](2026_09_23_independent_phase_v2_results.md), an ideal
8 cm baseline has at most about **2 microradians RMS** of geometric phase left
after independently fitting a phase offset and frequency slope in each short
dwell. This is an upper bound over **every baseline orientation**, so knowing
the reported 79° direction alone does not recover the information removed by
those nuisance fits.

The existing multirate phase discrepancies are roughly 0.05–0.36 radians. They
are descriptive, conditional estimator checks rather than independent noise
floors; nevertheless, the present evidence does not demonstrate the microradian
precision and calibration needed to use the remaining short-dwell curvature.
This quantifies a reason local phase tracking has not translated into better
satellite association or receiver position.

## Forward calculation

This is a forward-model sensitivity audit, not another fitted/held experiment.
It reads the frozen TLE/site selections and the 24 actual frame-reference times
in each of the 15 training dwells. No IQ is reopened, no held response is used,
and no receiver reference coordinate is supplied. The times span 104 ms within
each 120 ms capture; all frame opportunities are included without a phase mask.
Native RF is 11,209,687,500 Hz for every row.

For satellite position p, candidate receiver position r, and baseline b:

```
u(t) = (p(t) − r) / |p(t) − r|
phi(t) = (2 pi f_native / c) b dot u(t)
```

Propagation uses exact nominal SGP4 with the model's frozen causal TLE lines.
Positions are in the same ECEF frame. The unit direction u is dimensionless;
baseline is in meters and the wave number is in radians per meter. The 8 cm
length is the nominal mechanical benchmark, not a verified RF phase-center
measurement. Sensitivities scale linearly with assumed baseline length.

Within each dwell, remove the least-squares polynomial in centered time from
all three components of u. Degree zero profiles a free phase intercept; degree
one additionally profiles a differential frequency; degree two also profiles a
differential frequency rate. If U_res is the resulting matrix, the maximum
possible phase RMS for any fixed 8 cm baseline orientation is

```
(2 pi f_native / c) × 0.08 × largest_singular_value(U_res) / sqrt(frame_count).
```

This orientation-free bound does not require interpreting “axis is 79deg east.”
The artifact also evaluates one explicitly hypothetical interpretation:
horizontal baseline, bearing 79° clockwise from north, rotated from local ENU
to ECEF. That scenario is not an update to the station calibration or a claim
about RX0/RX1 wiring.

## Amount of geometric phase retained

The table reports the largest orientation-bound RMS over all 15 dwells.

| Hypothetical dual-RX phase nuisance fit in each dwell | GLRT-selected geometry | Phase-selected geometry |
|---|---:|---:|
| Phase intercept only | 0.009464 rad | 0.009223 rad |
| Phase intercept + differential frequency | 2.045 × 10⁻⁶ rad | 1.943 × 10⁻⁶ rad |
| Above + differential frequency rate | ~1.8 × 10⁻⁹ rad | ~1.5 × 10⁻⁹ rad |

Under the hypothetical 79° horizontal interpretation, the corresponding
intercept-plus-frequency results are 1.507 and 1.205 microradians. They are
smaller than the orientation-free maxima, as required.

The nanoradian entries are only double-precision frozen-model remainders after
removing three polynomial terms. They are **not** predictions of achievable
measurement precision, physical uncertainty bounds, or reliable TLE accuracy.
The nuisance-projection calculation is unweighted sensitivity analysis, not
a noise-weighted Fisher-information or detection-limit estimate.

## Empirical phase context

These previously published phase discrepancies come from the
[multirate analysis](2026_09_23_phase_association_and_motion.md). They concern
different captures and source conditions from the forward-model arc above.

| Sample rate | Supported native dwells | Native later-B versus A-curve median | Refined pilot median |
|---|---:|---:|---:|
| 2.5 MS/s | 3/8 | 0.364 rad | 0.0766 rad (3 dwells) |
| 10 MS/s | 8/8 | 0.224 rad | 0.0468 rad (7 dwells) |
| 15 MS/s | 7/8 | 0.225 rad | 0.0585 rad (6 dwells) |

The historical method fits receiver-relative CFO, optional CFO rate, fractional
delay, a phase convention, and a complex frequency response. Its complex response
is learned from the first 60 ms, and the phase curve is selected with A-band
interleaved cross-validation before refitting to all A times. Later B-band
checks therefore have conditioning and time-support dependencies. These old
time-half checks are historical development evidence, **not newly performed
validation and not the user's requested random-holdout protocol**.

The table must not be used as an independent noise floor, a cross-rate causal
comparison, or a significance test against the geometric bound. It shows that
the currently documented estimator agreement is orders of magnitude coarser
than the residual curvature after per-dwell phase/rate removal. Such fits also
remove most of the very directional signal we want to use.

## What continuity could change

As a deliberately counterfactual calculation, fit **one** phase offset and
frequency slope across the 39.003-second union of training frame times instead
of separate fits per dwell. The orientation-bound geometric RMS then rises to
0.2844 rad for the GLRT-selected solution and 0.2709 rad for the phase-selected
solution. Allowing one quadratic term leaves 0.02985 and 0.02771 rad.

Those are sensitivities to geometry within each model, not separation between
the two candidates, and not proof that either model is correct. They are not
available measurements: the present contract explicitly does not establish phase
continuity across retunes. Joining plotted phase curves, unwrapping independently
referenced dwell phases, or assuming a common electrical phase would invent
that missing calibration.

## Consequence for association and motion

The useful route is to preserve or independently calibrate the receiver phase
terms over a sufficiently long interval, rather than fit them freely in every
dwell and interpret the remaining curve as satellite motion. This requires
verified phase-center geometry and receiver mapping, an electrical phase/delay
model with a validity interval, and evidence that source-isolated complex phase
can be transported across the chosen interval. A continuous fixed-frequency
capture could be useful only if those continuity conditions are demonstrated.

The previously plotted [August 23 fixed-tuning example](2026_09_22_continuous_dual_rx_phase_glrt.md)
cannot provide that authority: it predates the continuity-buffer fix, lacks
device counters, and its prominent phase transitions align with refill
boundaries. Fixed tuning by itself is not enough. Any reuse of the existing
continuous-recording corpus must first establish counter-qualified RF time and
source continuity rather than use stored-sample time as elapsed RF time.

A separate [August 25 post-fix example](2026_09_22_phase_estimation_resolution.md)
does have verified counter continuity over the analyzed one-second interval.
Its pilot and broadband estimators reproduce rapid differential-phase evolution
after matched-support corrections, but the report explicitly leaves its physical
receiver/channel cause unidentified. Thus suitable stored timing evidence exists
for further source-isolation/calibration work; counter continuity alone still
does not turn that phase into a geometric observable. The present September
8 cm benchmark is not retroactively asserted as that capture's RF geometry.

The operator's 79° observation helps describe a possible orientation, but does
not supply the missing phase/delay stability, baseline sign, tilt, or RF
phase-center positions. Even with calibration, one baseline plus Doppler gives
only limited velocity projections, as shown in the
[observability audit](2026_09_23_phase_geometry_observability_audit.md); full
satellite speed, direction, identity, and receiver position remain unverified.

Any future calibration/association comparison must use the already documented
seeded random whole-group protocol and new frozen evaluation data. No estimator
was promoted, no immutable station contract was changed, and no RF was collected
for this audit.

## Reproduction

- [Forward-model artifact](figures/2026_09_23_independent_phase/geometry-sensitivity/results.json)
  includes the model and training-frame hashes, each dwell's timespan, projection
  dimensions, singular values, and both orientation treatments.
- [Forward tool](../tools/research/audit_independent_phase_sensitivity.py) and
  [three tests](../tests/tools/test_independent_phase_sensitivity.py) verify the
  nuisance projection, attainment/rotation invariance of the orientation bound,
  and nominal horizontal baseline construction.
- [Empirical context](figures/2026_09_23_independent_phase/geometry-sensitivity/empirical-context.json)
  and its [reader](figures/2026_09_23_independent_phase/geometry-sensitivity/build_empirical_context.py)
  reproduce the historical multirate counts/medians from hashed summary and CSV
  inputs without IQ access or refitting.
- The original model and phase extraction/scoring code remain unchanged.
