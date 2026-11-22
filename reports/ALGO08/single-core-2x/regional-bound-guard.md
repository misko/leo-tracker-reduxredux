# Far-exterior veto gated by the selected optimizer bounds

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

The solver hook already has the Graph tracks, so only the second column of CPU measurements is incremental when the gate activates. An interior pair bypasses that work. These measurements rebuild only the diagnostic, without a new position fit or publication. The component tests cover representable optimizer limits, signed and cavity pair selection, fallback on missing evidence, unchanged nonvetoed packet creation, and restoration when the experimental scope exits. [Component tests](../../../tests/pipeline_eval/test_regional_bound_guard.py)

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
