# Existing multi-scan positioning evidence

Source/report review only. No new model or experiment is frozen, and no recording
evaluation, optimizer job, reserve inspection or RF collection was performed.
The purpose is to preserve prior evidence before revisiting the user's original
question about continuous Kalman-like positioning.

## What has actually been tested

| Prior work | Evidence | What it does not establish |
|---|---|---|
| [Iteration1 DS16 spread](../2026_10_08_position_error_iter01/README.md) | Retrospective coordinate mean was 0.737 km from reference; coordinate median was 0.484 km. Causal robust fusion was proposed. | Those aggregates used future scans; they are not causal estimates or a new per-scan mean-error result. |
| [Iteration3 follow-up](../2026_10_08_position_error_iter03/README.md) | Again proposed causal multi-scan estimation for the stationary installation, with cold-start and latency reporting. | A proposal is not a completed receiver-position filter. |
| [DS3/DS4 surface fusion](../2026_09_25_ds3_ds4_surface_fusion/REPORT.md) | Reference-free sealed batch surface inference: full DS3 0.693 km, full DS4 1.667 km, combined 147 scans 1.303 km. Primary eight-scan group medians were 4.545 and 3.891 km; one DS4 group was a 15.046 km outlier. | One good full-batch estimate did not generalize to the other dataset or small groups. These are joint/window errors, not standalone errors or online-filter performance. |
| [DS1/DS2 comparison](../2026_09_24_ds1_ds2_final_comparison/REPORT.md) | Equal-weight joint multi-scan inference was completed. DS2 baseline joint error was 1.939 km; the consistent cap-800 joint result was 1.735 km. | Receipt-bound causal orbit predictions do not make an all-session receiver-position estimate an online causal filter. |

The [DS3/DS4 method contract](../2026_09_25_ds3_ds4_surface_fusion/METHODS.md)
explicitly excluded reference coordinates and source error fields from inference.
It interpolated each adaptive objective surface onto a common supported grid,
averaged capped MSE with equal whole-scan weights, then attempted a qualified local
quadratic refinement. Subtracting each scan's minimum was an invariance control.
IQR-scaled and fractional-rank surfaces were additional fixed sensitivities.
They did not improve full-corpus generalization. The full DS4 result worsened
relative to the earlier selected-point aggregate despite a smooth qualified fit.
This is evidence against assuming that more scans, objective rescaling or a good
local Hessian necessarily remove coherent bias.

The [DS2 execution inventory](../2026_09_24_ds2_sep24_inventory/rerun-plan.md)
also records a rejected legacy joint-session L-BFGS-B approach and a completed
shared-NORAD rate experiment with zero selected NORAD overlap across its sessions.
Neither its optimizer failure nor its zero-overlap finding should be assumed to
transfer unchanged to newer cohorts. Both must be remembered before rediscovering
the same proposal without checking the new inference inputs.

No demonstrated causal B7 receiver-position filter was found in the reviewed
iteration reports. This is a bounded review finding, not proof that no other
repository artifact exists. Historical phase/frequency Kalman experiments concern
carrier tracking; they do not by themselves validate geographic position filtering.

## Why a causal filter remains plausible, but unproven

Changing satellite geometry may contribute complementary geographic constraints.
A static joint position or a general position/velocity filter could combine them
without a known-location initialization: the first ordinary qualified inferred
position, or multiple retained ordinary hypotheses, supplies the initial state.
An ordinary hypothesis position is not a reference coordinate.

However, scans can share TLE errors, receiver calibration drift, orbit identities,
sampling patterns and overlapping inputs. Treating them as independent Gaussian
position fixes can shrink covariance while preserving systematic displacement.
A single local Hessian is not calibrated measurement covariance, particularly
after mixture association and nuisance fitting. Per-recording clock coefficients
also use local time centers, bases and gauges; copying them into a continuous
state is not automatically a physically consistent clock transfer.

Static fusion needs an explicitly documented stationary operating mode; it cannot
infer stationarity from knowledge of the reference location. A moving receiver
instead needs a motion-appropriate process model, uncertainty growth through gaps
and explicit reacquisition/change rules. Robust rejection can protect against
outliers but can also lock onto a wrong initial basin or reject real motion.
These tradeoffs require measured evidence rather than location-specific tuning.

## Minimal diagnostic before another fusion experiment

This is a prerequisite list, not an execution authorization or a frozen protocol:

1. Establish chronological session membership, observation availability timestamps,
   shared-session/IQ dependencies and gaps using existing sealed metadata. Record
   whether stationarity/movement is independently documented. Do not fill missing
   scans or merge duplicated evidence silently.
2. At ordinary reference-free endpoints, describe consecutive position increments,
   satellite-geometry/support changes, repeated satellites and calibration/TLE
   dependencies. Distinguish changing geometry from repeatedly measuring a shared
   bias. No reference coordinate selects sessions, gates or operating mode.
3. Before a later filter, establish a defensible measurement-uncertainty model and
   clock-state transfer convention. Freeze any learned covariance/process-noise
   calibration on training recording groups and retain conservative uncertainty
   and reacquisition when information is weak. Do not fit a noise model separately
   to each scan's reference error.
4. A later evaluation must keep matched fitted-c/c=0 inputs and policies. Report
   cold start, elapsed time and number of scans to each estimate, latency, outages,
   failure/reacquisition, motion lag and full coverage. Use ordinary independent
   positions as a comparator; a future-aware smoother is a separate comparator.

**Chronological processing is an algorithmic requirement, not a validation split.**
A causal filter may use only observations available by the reported estimate's
timestamp. Parameter training/validation must separately honor randomized whole
recording/dependency groups, with both receivers kept together and any shared-IQ
or declared temporal blocks kept intact. Any sequential test unit must preserve
its internal time order and cannot inherit a hidden state trained on its withheld
members. These already consumed cohorts are not newly unseen validation, and a
chronological tail must not simply be relabelled an independent holdout.

**The sequential/static-window metric never replaces the standalone goal.**
One aggregate position error, per-update causal errors after warm-up, and mean
individual-scan error are different quantities. Improvements to the first two
must be reported alongside the unchanged third, with their extra measurements
and latency made explicit. No result reviewed here establishes the current
standalone mean-position-error goal through continuous filtering.
