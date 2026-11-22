# Local time moments for broad association

All-observation time moments reduced broad discovery and exact cold ranking CPU from **4.400 to 1.357 seconds (3.24×)** on the longer DS30-0374 recording. Complete saved-detection-to-grid CPU fell from **28.786 to 25.914 seconds (1.11×)**. Both calibration positions, published owners, conditional RF RMS, optimizer paths, and every grid value matched on DS30-0374, a short physical recording, and two public simulated offers. The northern offer still produced two false boundary fixes.

## Proposal likelihood

Each curved track is divided into 20-second bins anchored to its first observation. Within each bin, three nodes at the endpoints and the observation nearest the midpoint supply a quadratic interpolation of orbital Doppler and its phase tangent. Bins with at most three observations keep every timestamp. The proposal projects all frequency observations onto an orthonormal basis for constant, linear and quadratic time terms. It also keeps the squared residual energy orthogonal to that basis. Adding this energy to the projected residual energy gives the original white-noise curve score, including the Gaussian offset prior and native alias, whenever the orbital prediction agrees with the interpolating polynomial. The original counts and time moments feed the release's shared receiver and orbit-phase proposal. [Prototype](../../../tools/pipeline_eval/variants/algo08_track_moments.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_track_moments.py)

The prototype uses the same catalogue, four centre seeds and four corner proposals. Their broad curve ranking uses approximate orbital frequency and checks visibility at the nodes. It keeps full curved-track eligibility and all observation IDs. Sparse seed calibration, discrete alias selection, cold branch scores, and up to three refreshed regional fits all use the original observation times and release numerical routines. An empty full-data gate repeats stock initial discovery. The original conservative recovery, history policy, signed inference, cavity decision, dual calibration results and full grid run after branch selection. The only geometric context used is the supplied regional offer and causal orbit archive.

The earlier sampled proposal discarded observations in discovery and in two early fits. The collapsed schedule reduced later fitting stages and changed the evidence admitted to publication. The time-moment experiment preserves full observed energy in broad discovery and retains every subsequent solver stage. An interpolated orbital score can still change the branch set before full scoring. [Sampled proposal](solver-sampled-initial.md) · [Collapsed schedule](solver-collapsed.md)

## Saved-input comparisons

Each pair used identical verified detection bytes, a common regional offer, one pinned low-priority CPU and the frozen numerical runtime. Both arms included causal parser reuse and coarse salvage statistics. The timed run starts at saved detections and ends at full selected packet and grid construction. It excludes waveform acquisition and rendering. Each row has one timed pair. DS30-0016 and north-far ran moments first. DS30-0374 and the southern offer ran the control first. [Trial runner](solver_track_moments_trial.py)

| Saved input | Observations / orbital nodes | Catalogue | Broad and exact cold rank CPU s, control → moments | Initial context and selection CPU s | Solve and grid CPU s | Solve and grid elapsed s |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0374 | 2,918 / 483 | 1,407 | 4.400 → 1.357 | 6.954 → 4.020 | 28.786 → 25.914 | 29.222 → 26.202 |
| DS30-0016 | 127 / 18 | 1,449 | 0.294 → 0.086 | 0.370 → 0.163 | 4.660 → 4.411 | 4.733 → 4.475 |
| South containing | 266 / 84 | 1,615 | 0.497 → 0.275 | 0.804 → 0.493 | 6.429 → 6.242 | 6.473 → 6.299 |
| North far | 285 / 90 | 1,569 | 0.635 → 0.377 | 1.216 → 0.957 | 11.544 → 11.203 | 11.671 → 11.373 |

DS30-0374 had six distinct ranked assignments with moments and seven with the control, with three in common. Both original top-three lists included the same winning assignment and two different alternatives. The winning aliases and all 2,467 accepted gate points matched. The broad association evaluated 19.0 million catalogue-by-node cells, down from 115.0 million catalogue-by-observation cells under the same call schedule. Peak process RSS fell from 994 to 776 MiB on this pair. The earlier time-spread sampler changed the final owners on the same recording. [Sampled proposal results](solver-sampled-initial.md)

South containing had two distinct ranked assignments with moments and three with the control. The selected assignment and aliases matched. DS30-0016 and north-far kept the complete ordered ranked assignments. Each grid matched field for field after dropping the elapsed time, with 179 evaluations on the three containing offers and 137 on the wrong offer. Both north-far runs made the same cavity offer and published the boundary solutions. Both arms retained the values below.

| Input and calibration arm | Position in both runs | Horizontal error (km) | Solver RF RMS (Hz) | Published owners |
|---|---|---:|---:|---:|
| DS30-0374, `c = 0` | 37.849625, −122.464635 | 1.855 | 101.536 | 2,905 |
| DS30-0374, fitted `c` | 37.850682, −122.463809 | 1.935 | 101.520 | 2,905 |
| DS30-0016, `c = 0` | 37.834938, −122.491301 | 1.644 | 109.375 | 109 |
| DS30-0016, fitted `c` | 37.835682, −122.494190 | 1.662 | 109.479 | 109 |
| South containing, `c = 0` | −32.957865, 21.464955 | 0.826 | 6.503 | 266 |
| South containing, fitted `c` | −32.960748, 21.465586 | 1.109 | 6.392 | 266 |
| North far, `c = 0` | 47.785644, 16.798538 | 52.455 | 37.951 | 228 |
| North far, fitted `c` | 47.753706, 16.798538 | 52.491 | 37.533 | 228 |

The scorer applied physical and simulated truth after inference. On the southern containing offer, fitted calibration improved the RF RMS and increased horizontal error. [Physical reference](../location-audit/README.md) · [Simulation scores](../regional-release/blind-scores.csv)

The prototype accelerates the proposal stage. Its largest observed complete saving was 2.87 CPU seconds from saved detections, and the offer that excluded the receiver reproduced the stock false fixes. The two changed candidate sets leave broader association equivalence unverified.

## Reproduce

Run the two modes with the release assets, the same saved detector JSON and its independently checked SHA-256, the capture-time archive, and the same regional offer. The runner emits complete coordinates, owner maps, grid and branch signatures.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
for mode in control moments; do
  flock /tmp/leo-algo08v2-2x-bench/gauss.lock \
    nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_track_moments_trial.py \
    "$mode" "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
done
```

| Saved input | Detection SHA-256 |
|---|---|
| DS30-0374 | `e2589f75dce207f1732f1e05899484ebec47c2b93caf1d5ee0991c5a4ea89363` |
| DS30-0016 | `5e29a9c9f76c93e605792915f8baffe4a28e31dbd6bd67e586c6a68821bd9a2d` |
| South containing | `9ead12e735906a95066b77dfcaca54e9bdf68dc0a2c816a95fa3bca3419a3d49` |
| North far | `54ffd828f5cb9b09baa1d38e0f3fdff5b9e41954f74e60226e239fa5c6e4f1d8` |
