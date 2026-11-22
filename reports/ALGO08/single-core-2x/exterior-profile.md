# Fixed-owner position scores beyond the offered square

The best sampled exterior position scored lower than every sampled position in the offered square in both calibration arms on all three development offers. That includes the valid northern offer whose receiver was **100 m inside**. The wrong southern offer had smaller score gains than the valid northern offer in both arms. A rule triggered by the sign of the gain would lose both valid fixes. Raising a gain threshold enough to retain those fixes would miss the wrong southern offer on this sample.

The earlier boundary check used the constrained endpoint alone. An older halo experiment used disjoint-orbit fits with a separate smooth Doppler estimator. Here the existing ALGO08v2 selected-packet likelihood evaluates points on both sides of the same offered square. [Boundary study](edge-trial.md) · [Earlier halo evaluator](../../../tools/pipeline_eval/variants/region_halo.py)

## Selected packet and matched comparison

The runner starts from digest-verified public saved detections and the original causal TLE archive. The normal solver selects observations, satellite owners, alias assignments, model settings and a phase linearization for each calibration arm. The existing packet builder reproduces the selected endpoint objectives and evaluates the original full interior grid. The offline hook then reuses that packet's likelihood evaluator. Both arms score identical new positions and recompute the original nuisance calculation at each position, including the robust noise precisions, marginal volume, predictive contribution and elevation penalty. The owners, aliases, retained observation rows and phase linearization stay fixed at their selected values. The hook returns the ordinary packet to the solver. Evaluation reference positions enter only when measuring the errors in the table. [Trial runner](exterior_profile_trial.py) · [Published objective](../../../src/leo/analysis/localization_v3/reassociation_context.py)

The probe schedule was committed before scoring. It samples each face of seven concentric squares at distances of `1/512`, `1/128`, `1/32`, `1/8`, `1/2`, `1` and `2` times the offered width beyond the boundary. It includes corners, intermediate face positions, and normals projected through both endpoints and their width-relative tangential neighbors. Boundary and mirrored inward points supplement the complete published interior grid. A positive inside-minus-outside value means the sampled exterior has a lower objective. The inside minimum includes the boundary. [Prespecified geometry](../../../tools/pipeline_eval/variants/experimental/exterior_profile.py)

## Public development results

| Offered square | Arm | Published error (km) | Best exterior distance past face (km) | Best exterior error (km) | Inside minus outside objective |
|---|---|---:|---:|---:|---:|
| North, 100 m inside | Fixed zero | 0.106 | 0.781 | 0.886 | +0.457047 |
| North, 100 m inside | Fitted | 0.141 | 0.781 | 0.886 | +0.263995 |
| North, far omission | Fixed zero | 52.455 | 25.000 | 27.623 | +133.953379 |
| North, far omission | Fitted | 52.491 | 25.000 | 27.623 | +111.430563 |
| South, far omission | Fixed zero | 53.585 | 3.125 | 50.371 | +0.196314 |
| South, far omission | Fitted | 53.584 | 3.125 | 50.371 | +0.196278 |

All six endpoints reproduced the saved results exactly and lay on the offered boundary. All objective replay discrepancies were zero. The selected packets had 302, 228 and 114 published owned observations respectively, with the same owner map in both calibration arms within each offer. The three grids contained 483, 483 and 475 finite points per arm after adding the probes. The additional profiles took 1.990, 1.344 and 0.835 CPU seconds on one low-priority core. [Pointwise evidence](measurements/exterior-profile.json.gz) · [Near-edge offers and scoring](edge-trial.md) · [Published far-offer scores](../regional-release/blind-scores.csv)

Even a point 48.8 m outside the valid northern boundary improved the sampled objective by 0.0695 with fixed zero and 0.0626 with fitted calibration. The best sampled southern exterior point still lay 50.37 km from the receiver. The score can therefore continue downhill across an edge with an accurate constrained fix, and the amount of improvement does not track the magnitude of a wrong-region error in these controls.

The comparison uses a finite position sample and a likelihood conditional on the owners and linearization chosen for the original offer. A new search with full exterior association or phase relinearization could change the objective surface. This test stopped after the valid near-edge counterexample and the two completed far controls. The centered and close-omission offers were outside the final run. Two component tests cover the width-scaled geometry, common probe positions for both arms, distinct optima and a reported evaluation failure. [Component tests](../../../tests/pipeline_eval/test_exterior_profile.py)

## Reproduction

Run the trial once per public offer with the saved native detection file, its pinned SHA-256, the causal archive root and the frozen release assets. The representative lock command below uses the same environment as the measured runs.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/exterior_profile_trial.py \
  "$saved_detections" "$tle_archive_root" "$release/assets" "$offer" "$detector_digest"
```
