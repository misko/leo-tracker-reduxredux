# DS7 temporal transfer: sub-kilometre group result

The predeclared final chronological group achieves **443.02 m** with equal
averaging of eight independent fits. The first chronological group remains at
1,930.07 m with that same method. This is progress toward the active DS7 goal,
not proof of full-corpus or reliable per-group sub-kilometre accuracy. Distances
use the unchanged great-circle metric against the unsurveyed operator reference
at one previously exposed site.

| Frozen method | First group of eight | Final group of eight |
|---|---:|---:|
| Equal independent-position mean | 1,930.07 m | **443.02 m** |
| Inverse training-RMS-squared mean | 2,152.44 m | **602.41 m** |
| Mean of lowest-RMS 75% | 2,532.71 m | **446.91 m** |
| Joint static-site Doppler fit | 2,541.48 m | 1,322.09 m |

All group estimates are qualified: the joint fits converge away from bounds;
the controls use qualified upstream fits and preserve all eight declared input
members (the 75% rule subsequently retains six according to frozen training
RMS). The same scientific code, candidate policy, masks, priors and aggregation
rules were retained. The final group was chosen by chronology before its fits
or scores. No method, member or weight was selected using its geographic error.

Evidence: [first-group results](../2026_09_27_ds7_wave2/RESULTS.md),
[final joint score](coordinator/last8-score-v1/scores.json),
[equal mean](coordinator/controls-equal-group11-score-v1/scores.json),
[inverse RMS](coordinator/controls-inverse_rms2-group11-score-v1/scores.json),
[lowest RMS 75%](coordinator/controls-lowest_rms75-group11-score-v1/scores.json),
[pre-fit specification](TRANSFER-SPEC.md).

## Individual recordings and scope

All eight later individual fits converge and remain interior. Their reference
distances, in order 081–088, are 833.30, 1,973.20, 4,596.02, 1,704.44, 741.75,
1,735.32, 4,542.14 and 1,846.97 m. Two are below 1 km. Including the first eight
recordings, 16 distinct singles have been evaluated and two are below 1 km.
Neither numerical convergence nor low training RMS guarantees location accuracy.

Only two of the eleven chronological groups have been evaluated. The remaining
72 recordings are not yet prepared for this frozen estimator, and the pooled
full88 fit has not run. The 443 m result must not substitute for those missing
evaluations or close the broader goal. Equal averaging leads both evaluated
groups, but two groups from one site are insufficient for a population ranking.

## Diagnostics and execution

- The full producer trace verifies canonical 11.2 GHz normalization and alias
  removal before numerical export. A model-only RF rescaling would be wrong.
  [Frequency audit](frequency-units/README.md).
- The first-group joint fit worsens fixed-parameter held predictive density
  in seven of eight recordings. Partition-separated residual slopes are
  inconsistent; they do not independently calibrate receiver drift.
  [Residual audit v2](residual/README-v2.md).
- The combined exporter removes one real source load and one preparation call.
  Its 62-track/187-array check preserves scientific values and dtypes exactly.
  It took 108.62 seconds versus 125.33 seconds recorded for separate stages,
  under different host load; this is not a controlled causal speed ratio.
  [Equivalence evidence](preparation-performance/README.md).
- The original 1,200-second preparation deadline stopped the final bank.
  Its timeout is preserved. A separate predeclared completion lease reused the
  sealed export and built a fresh bank in 88.59 seconds. Final-group fitting
  consumed 329.48 of the 900 authorized adapter seconds. No new RF or raw IQ
  was used. [Input audit](review/LAST8-INTEGRITY-AUDIT.md).

The separate synthetic nonlinear clock-recovery prerequisite passed all three
predeclared cases: projected Jacobian rank 5/5, maximum position error 3.12 m,
timing error below 0.000209 s and slope error below 0.00758 Hz/s. All cases
converged/interior and consumed 142.93 analyzer seconds in total. These are
synthetic recovery errors relative to a generated position, not errors against
the site reference. This does not supply independent clock calibration or admit
a real-data correction. [Clock recovery evidence](clock-recovery/README.md).

Next work remains full-corpus coverage and matched evaluation of
the frozen joint model and aggregation controls, with bounded preparation and
all failures retained.

## Verification

All 80 relevant tests and Ruff pass. The coordinator verified 22 run/score
directory seals and exact source linkage for all eight estimates used by the
final-group controls. Dataset metadata remains valid; wave-1 and wave-2
closeout hashes remain unchanged. The earlier Terra audit recorded the group
as pending at its observation time; the [final source audit](review/final-group-source-audit.json)
now verifies its completed state. No evaluation worker remains active at
closeout; the broader DS7 goal remains active.
