# Far-exterior veto gated by the selected optimizer bounds

## Complete raw-I/Q publication on the same northern recording

The frozen guarded conditional build `f495615e14412b6b1aa88e7bebb44130543627f960c5e020bc8090652f4eb5d3` processed two previously published northern simulation offers. Both invocations used the same sealed raw recording, the same verified capture-time archive, one pinned core and separate empty output directories.

| Offered square | Unguarded result | Guarded terminal and web evidence | Guarded elapsed |
|---|---|---|---:|
| Receiver 100 m inside | Fix, fitted error 0.141 km | Same two positions, satellite owners, numerical path and grid, and all eight rendered images | 19.44 s |
| Center 64.93 km from receiver, correct region missing | False fix, fitted error 52.49 km | Withheld both positions, recorded `both_receivers_support_far_exterior`, published zero fix images and no position grid or path | 20.64 s |

The runs validate the guarded candidate through acquisition, conditional residual scanning, solving and publication. The unguarded values come from the preceding frozen comparison. The elapsed values are candidate-only timings. On the saved four-case DS30 stage, none of the verified candidate endpoints touched the optimizer bounds, so none would request the extra test. That endpoint check does not measure the guarded build's DS30 runtime. The saved public two-site dataset still has four near omissions the guard misses. [Inside publication](measurements/guard-north-inside-single.json) · [Distant omitted publication](measurements/guard-north-far-single.json) · [Earlier unguarded endpoint](measurements/north-far-conditional-solver.json.gz) · [Four DS30 endpoint checks](measurements/conditional-four-boundary-check.json)

The optional saved-solver guard dispatches the far-exterior diagnostic only if at least one selected calibration arm reaches a native optimizer bound. Six of the ten public offers activate it. It vetoes both far omissions, retains all four valid fixes, and misses all four near omissions. The guard stays outside the frozen publication candidate. [Earlier ten-offer result](regional-exterior-veto.md) · [Experimental hook](../../../tools/pipeline_eval/variants/experimental/regional_bound_guard.py)

## Endpoint gate

The selected signed pair or accepted cavity pair supplies its original `endpoint_east_north_km` values before figure packet creation. A coordinate activates the check if it lies at the signed box limit or one representable binary64 step inward. This allows for one rounding step in the box update. The gate uses neither rendered coordinates nor a geographic margin. Missing, malformed, or out-of-box endpoint pairs cannot activate the diagnostic. [Compact optimizer](../../../tools/pipeline_eval/variants/compact_cavity_optimizer.py)

After activation, the guard takes the same Graph tracks and reads the past-only TLE catalogue using the capture cutoff. It scores the original four inside radii and four exterior radii for both receiver groups with the same visibility and contrast likelihood. The frozen two-receiver rule determines whether to withhold both arms before building the figure packet. When the diagnostic is unavailable, incomplete, or does not vote to withhold, the original figure packet receives the selected pair. [Frozen veto geometry](regional-exterior-veto-protocol.md) · [All-track score](regional-reassignment.md)

## Saved-path audit

The original six regional publications, two archived containing-edge solver packets, and both mirrored outside publications supplied local endpoints for the complete ten-offer audit. Each reported endpoint matched the last saved optimizer round and the conditional grid endpoint. The runner joined the publications to the saved probes by the offered center and width. Neither evaluation coordinates nor installation identity enters the gate or the scorer. No offer's gate status was unknown. [Saved audit runner](regional_bound_guard_trial.py) · [Original publications](../regional-release/README.md) · [Mirrored publications](mirrored-regions.md)

| Public offer | Arms on bound | Diagnostic runs | Result |
|---|---|---|---|
| North, centered | None | No | Keeps valid fix |
| North, 100 m inside | Both | Yes | Keeps valid fix |
| North, 100 m outside | Both | Yes | Misses omission |
| North, 1.5 km outside | Both | Yes | Misses omission |
| North, far omitted | Both | Yes | Vetoes omission |
| South, centered | None | No | Keeps valid fix |
| South, 100 m inside | None | No | Keeps valid fix |
| South, 100 m outside | None | No | Misses omission |
| South, 1.5 km outside | Both | Yes | Misses omission |
| South, far omitted | Both | Yes | Vetoes omission |

All activated arms were exactly at the bound. The southern 100 m omission left the two optimizer endpoints 242 m and 183 m inside the offer. The gate therefore cannot use the exterior score there. The northern containing-edge pair paid for the diagnostic and kept both fixes. These are replayed decisions on two public simulated captures. [Southern mirrored control](geographic-input-audit.md)

## Rebuilding the score from saved detections

The northern near-edge and far offers used the same digest-verified saved detections. The trial rebuilt the Graph inputs, converted them to the representation the compact solver passes to inference, and ran the guard's scorer with the original causal archive. All 96 probes per offer reproduced their coordinates, pooled and receiver scores, and track owners exactly. The catalogue counts and contributing causal snapshot digests matched too. The near-edge offer remained publishable and the far offer withheld both arms. [Saved endpoints and replay measurements](measurements/regional-bound-guard.json)

| Northern offer | Graph preparation CPU (s) | Incremental catalogue and probes CPU (s) |
|---|---:|---:|
| 100 m inside | 0.127 | 2.830 |
| Far omitted | 0.126 | 2.775 |

The solver hook already has the Graph tracks, so activation adds the catalogue and probe cost. An interior pair bypasses that work. These measurements rebuild only the diagnostic, without a new position fit or publication. The component tests cover representable optimizer limits, signed and cavity pair selection, fallback on missing evidence and archive errors, unchanged nonvetoed packet creation, and restoration when the experimental scope exits. [Component tests](../../../tests/pipeline_eval/test_regional_bound_guard.py)

The experiment opts in by wrapping one saved solve in `bound_exterior_veto(archive)`. To repeat the independent audit and scorer measurement, use the original public publication root, the existing southern mirrored publication, and the northern saved detections already pinned in the probe packet. [Replay inputs and thresholds](regional-exterior-veto-protocol.md)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/regional_bound_guard_trial.py "$public_output_root" \
  --extra-publication "$south_mirror_root" "$south_mirror_run" \
  --rescore north-edge "$north_saved_detections" "$public_archive" "$release/assets/tracks.json" \
  --rescore north-far "$north_saved_detections" "$public_archive" "$release/assets/tracks.json"
```

## Research publication opt-in

Freeze a separate research bundle with `--regional-veto`. The generated specification records `"regional_veto": true` and pins the boundary guard, exterior decision rule and all-track scorer. The launcher uses the same supplied archive path as the compact solve. Existing bundles keep their earlier specifications and sources. Use distinct guarded bundles for the stock receiver and any experimental capture schedule. [Freezer](../../../tools/pipeline_eval/qualification/freeze_publication.py) · [Research publisher](../../../tools/pipeline_eval/qualification/experimental_publication.py)

```sh
PYTHONPATH="$PWD:$PWD/src:$release" "$release/venv/bin/python" -B \
  -m tools.pipeline_eval.qualification.freeze_publication "$guarded_stock_build" \
  "$release/assets/cancellation-factors.so" f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809 \
  --solver stock --ingress stock --regional-veto
```

The standard publication records a veto as `both_receivers_support_far_exterior`. Both calibration coordinates are absent, and the normal withheld publication omits the path, grid and eight fix figures. The publication test stubs acquisition, numerical inference and rendering while using the real scan application and stores. It checks that the same numerical fix publishes normally with the flag disabled, and that contained fixes keep their eight figures with the flag enabled. Forty-nine component tests passed. The ten saved simulated offers provide the existing geographic development evidence, including four missed near omissions. [Publication boundary tests](../../../tests/pipeline_eval/test_regional_veto_publication.py)
