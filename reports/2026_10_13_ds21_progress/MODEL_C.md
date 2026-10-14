# Model C: joint native association

Status: implemented; five-recording shared-proposal development comparison
complete. This is an interim report; the full DS21 0.5 km target is unmet.

The latest [DS21-009 fixed-policy coverage transfer](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_009_RESULTS.md)
completed 18 C calls, 17 stationary. All/low/high errors improve to
**1.152329 / 1.297634 / 1.578834 km** from
**1.595252 / 4.547625 / 1.758365 km**. Combining now beats both halves, but
none meets 0.5 km. All selected boundary flags are false. The all/`cold-2`
start fails the unchanged stationarity criterion despite solver success and
remains recorded without retry. The candidate pool and proposals change with
coverage; this is not an isolated calibration-model improvement.

The earlier [DS21-013 coverage-conditioned comparison](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_013_RESULTS.md)
completed 18 C calls, 16 stationary. All/low/high errors are
**1.846733 / 3.104978 / 1.065469 km**, versus the original
**267.759878 / 271.452943 / 198.398059 km**. Combining improves on the low half
and worsens the high half; none reaches 0.5 km. The failed all/cold-2 and
low/shape-low starts remain excluded under the original stationarity threshold.
All three selected boundary flags are false. This control recovers useful
initialization on one case while leaving a smaller localization error unresolved;
the historical table and full-DS21 target remain unchanged.

The model fits position and calibration while marginalizing satellite identity,
native measured frequency branches and clutter. Physical Doppler uses each
observation's RF. These fast scans have zero validated temporal edges and neutral
waveform weights, so this comparison measures per-window joint association,
not confirmed satellite tracking.

| Development recording | CH1–4 km | CH5–8 km | CH1–8 km |
| --- | ---: | ---: | ---: |
| DS21-001 | 5.791 | 3.293 | 1.425 |
| DS21-003 | 3.839 | 0.850 | 1.957 |
| DS21-005 | 0.644 | 3.714 | 1.556 |
| DS21-023 | 4.579 | 5.058 | 4.899 |
| DS21-039 | 3.759 | 2.557 | 4.291 |

All results use fitted `c`. CH1–8 median is 1.957 km and maximum 4.899 km;
0/5 are below 0.5 km or 1 km. Half-band runs inherit all-training ambiguity
initialization, so they are not fully independent band-only pipelines.

Preserving all native within-cell candidates later improved DS21-005 to
0.909 km but worsened DS21-023 to 5.149 km; that mixed control was not promoted.
Its half-band comparisons have not been rerun, so it cannot be used to claim an
isolated improvement from combining bands. Weak receiver-pair coupling also
worsened the matched position comparisons despite improved convergence.

The completed DS21-039 diagnostic crosses full/half-band geometry and satellite
timing with full/half-band physical calibration on identical native observation
support. It reports satellite, ambiguity-cell and sampling-integer posteriors,
visibility and clutter. A separate coordinator diagnostic uses the same window
likelihoods to assess observation weighting and block concentration. Full/half
states change satellite-or-clutter assignments in 18–20% of windows. No RF-scaling
error was found; calibration, timing and association interact.

An additional 18 fixed-position profiles and seven warm/free continuations on
DS21-039 exposed a missed optimizer basin. The unchanged all-band objective
improved from 33,172.423 to 32,380.955, but post-seal position error improved only
from **4.291 to 4.073 km**. This is a separate development control with extra
search effort, not a replacement for the matched five-case table above. It
remains worse than the historical high-only result and does not meet 0.5 km.
The [refinement report](../2026_10_13_ds21_039_root_cause/REFINEMENT_RESULTS.md)
retains all outcomes. The subsequent three weighting controls gave 4.314, 4.106
and 4.592 km; the winner-preserving native-candidate prior gave 4.410 km against
the matched 4.073 km baseline. All sixteen new fits were stationary. None of
these changes is promoted; better frequency fit again failed to improve accuracy.

Four matched receiver RF fits then added one opposite-sign receiver slope while
keeping common `c` fitted. All were stationary. The selected contrast was
17.471 Hz/GHz, but position error worsened from 4.073 to 4.085 km despite a small
objective improvement; this is also not promoted. A separate zero-optimizer
block-residual audit found persistent receiver/band structure with unstable
cross-products and nearly unsupported channel tails. It does not establish a
stable shared-noise covariance or a hardware clock fault.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.

The additional [DS21-007 baseline](../2026_10_13_ds21_release_readiness/JOINT_007_RESULTS.md)
completed 18 stationary fits. All/low/high errors are 3.524 / 3.738 / 4.325 km,
with fitted c throughout. The all-band result improves on both halves but misses
0.5 km. Half-band fits inherit all-training ambiguity initialization. This new
case is separate from the original five-case matched A/B/C table.

The subsequent [DS21-009 fitted-only three-model comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md)
completed another 18 stationary C fits. All/low/high errors are
**1.595252 / 4.547625 / 1.758365 km**; combining bands improves on both halves,
but all three miss 0.5 km. C uses the original native objective at scale one and
the unchanged six all-training receiver lifts, each derived once and shared
across views. All B/C views also inherit the common discovery bank and physical
proposal initialization. C's all-band posterior frequency RMS of 95.538 Hz is
not a position confidence bound. All 54 A/B/C calls and 12 reviewed outcomes
were sealed before reference evaluation; the historical five-case table remains
unchanged, and no algorithm is selected by its per-case reference error.

The subsequent [DS21-011 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md)
completed 18 stationary C fits. All/low/high errors are
**0.479573 / 1.080449 / 3.818150 km**. CH1–8 passes 0.5 km on this development
case and improves on both halves. All selected physical boundary flags are false.
The winning combined proposal is `shape-all`, selected by training objective
before the reference join. This single passing case does not establish full-DS21
performance or justify selecting a different model for each known reference.

The subsequent [DS21-013 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_013_RESULTS.md)
has severe all/low/high misses of **267.759878 / 271.452943 / 198.398059 km**.
Sixteen of 18 C fits are stationary. C/all `shape-low` start 3 retains KKT
235.230587 after 20.063 seconds; C/low `cold-2` start 2 retains KKT 0.001292600,
above the fixed 0.001 threshold despite solver success. Neither was retried or
accepted by loosening the check. Training selects `cold-0` for all/low and
`cold-2` for high; selected boundary flags are false. C's native seeds and six
all-training receiver lifts are unchanged, so no cause is assigned to B's
separate fallback. The independent post-seal audit finds the configured reference
outside every original proposal disk despite being inside the regional prior.
Why discovery missed is unresolved; a reference-blind coverage control must
precede further expansion. The DS21-011 passing case does not establish generality.
