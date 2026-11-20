# Receiver and positioning algorithms

**Active development, November 20, 2026.** Use **algo07v5 fast, no repair** as the accuracy reference and **compact v5, five-refresh secant** as the smaller receiver under development. The four v5 configurations and compact v5 can all consume the same saved GLRT detections. The deployed fast-scan Standard path has its own production identity, **ALGO07**. [Original DS26 evaluation](docs/analysis/algo07v5-ds26-performance.md) · [Compact evaluation](reports/2026_11_19_receiver_screening/secant-full/README.md) · [Production release](reports/ALGO07/README.md)

## Active algo07 variants and compact v5

| Algorithm | Status | What it does | How to select it |
|---|---|---|---|
| **algo07v5 fast, no repair** | **Active reference** | Forms tracks from native GLRT detections, matches causal satellite orbits and fits receiver position. Runs its late selection and produces the scientific archive and diagnostic figures. | `replay --role baseline` |
| **Compact v5** | **Active development** | Shares the early satellite search across calibration fits, keeps five orbit updates, uses bounded secant position fits and publishes after checking the result with one satellite family left out at a time. | `run --variant v5_secant_fit` |
| algo07v5 selective gap | Active comparison option | Screens timing-gap fragments with the incumbent fit before paying for independent annotation and inclusion. | `replay --role selective-gap` |
| algo07v5 one omitted track | Active comparison option | Proposes at most one previously unowned track for independent recovery. | `replay --role omitted-track-one` |
| algo07v5 two omitted tracks | Active comparison option | Proposes up to two previously unowned tracks. Each can trigger further fits and admission checks. | `replay --role omitted-tracks` |
| Original-schedule GLRT + compact v5 | Active receiver integration | The standalone C detector reads authenticated saved dual-antenna I/Q, extracts pilots and hands its new detections to the compact position program. | `python -m tools.pipeline_eval.portable_receiver` with the recording and CPU arguments below |

The four `--role` names reproduce the fast-v5 study policies. A standalone `leo-algo07v5` request selects its own explicit scientific policies. The full label matters when comparing timed runs. [Repair policies](docs/analysis/algo07v5-accuracy-repair.md) · [Standalone v5 policy flags](docs/how-to/evaluate-algo07.md)

### Run the active receivers

Run from the repository root. These commands list the algorithms and read committed scores on a fresh checkout, including on a machine without the radio archive.

```sh
uv sync --locked
work=$(mktemp -d)
.venv/bin/python -m tools.pipeline_eval list
.venv/bin/python -m tools.pipeline_eval baseline --panel ds26-all159
```

To recompute the archived roof positions, use the evaluation host with its recording inputs and frozen v5 release. The release binds the absolute path and digest of the SciPy BLAS library as well as CPython 3.12.14, NumPy 2.5.2, SciPy 1.18.1, SGP4 2.27, Matplotlib 3.11.1 and Pillow 12.3.0. The original evaluation checkout already has that environment. In a separate fresh checkout on that host, point its `.venv` at the installed release before running either receiver.

```sh
# Only for a new replay checkout without a .venv
ln -s /home/mouse9911/gits/leo-tracker-reduxredux/.venv .venv

work=$(mktemp -d)
.venv/bin/python -m tools.pipeline_eval replay --panel smoke --case DS29-0082 \
  --role baseline --require-inputs --pin --out "$work/original"
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS29-0082 \
  --variant v5_secant_fit --require-inputs --pin --out "$work/compact"
```

Use any of the other three `--role` values from the table in the same replay command. `--role all` runs all four original configurations. A fresh non-roster compact fit can instead use the standalone executable. On Linux with a C compiler and the project numerical dependencies, install into a new directory and pass the native GLRT document, graph-track configuration, capture-time TLE archive and search region. SHA-256 values bind the actual files. The tile and visibility-screen centers are latitude and longitude in degrees.

```sh
.venv/bin/python -m tools.pipeline_eval.cavity_runtime "$work/cavity"
.venv/bin/python -IB "$work/cavity" \
  --native "$NATIVE" --native-sha256 "$NATIVE_SHA256" --session "$SESSION_ID" \
  --track-config "$TRACK_CONFIG" --config-sha256 "$CONFIG_SHA256" \
  --archive "$TLE_ARCHIVE" --tile "$TILE_LAT" "$TILE_LON" \
  --screen-center "$SCREEN_LAT" "$SCREEN_LON" --width-km 25
```

For a full saved-I/Q replay on the recording host, supply available CPU IDs, the installed compact receiver and a new output path. The host reader uses the recording account and a user systemd manager. The default installation profile is `compact`. Research profiles add a majority-support check (`majority`), wrapped longitude (`longitude`), earlier release of model memory (`phase-release`) or an interior-tile check (`interior`). [Standalone inputs and profiles](reports/2026_11_19_receiver_screening/next/cavity-payload/README.md) · [Receiver benchmark manual](tools/pipeline_eval/README.md) · [Measured complete I/Q replay](reports/2026_11_19_receiver_screening/native-receiver/portable-command/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.portable_receiver --case DS29-0082 \
  --cpus 3 4 5 6 7 --receiver "$work/cavity" --out "$work/from-iq"
```

### Read or reproduce the benchmark

The latest comparison includes 159 DS26 recordings, the 127-recording DS26 benchmark subset and the eight-recording DS29 benchmark. Both datasets use the same physical roof. Position curves count every recording. Geographic errors and conditional Doppler residuals are available separately for zero and fitted RF calibration. The four controlled desktop timing pairs start at saved GLRT. Separate historical runs provide the larger runtime distributions. [Runtime and position figures (PDF)](reports/2026_11_20_v5_runtime_position/v5-comparison.pdf) · [Recording-level CSV](reports/2026_11_20_v5_runtime_position/per-recording.csv) · [Timing protocol](reports/2026_11_19_receiver_screening/deployment/same-core-baseline/README.md)

```sh
.venv/bin/python reports/2026_11_20_v5_runtime_position/plot.py --out "$work/comparison"
.venv/bin/python -m tools.pipeline_eval figures --panel matched135 --out "$work/ten-directions"
.venv/bin/python -m tools.pipeline_eval benchmark --receiver original-support --out "$work/glrt"
```

The six named benchmark galleries are `fixed` (four versus five timing regions), `staggered` (timing-region schedule), `one-lane` (single acquisition lane), `antenna-confirmation` (antenna use and retries), `original-support` (preserving original pilot support) and `receiver-deadline` (acquisition and timing deadlines). Use their names with `benchmark --receiver`. To inspect other sealed studies, use `benchmark --study PATH --out DIR`. [All per-modification plots](reports/2026_11_19_position_atlas/README.md)

## Other algo07 implementations

| Implementation | Status | What it does and how to run it |
|---|---|---|
| ALGO07 production | Production default for fast-scan Standard positioning | Proposes guarded whole-family satellite reassociation after ALGO06. Rejection preserves the incumbent. The production identity is `algo07-causal-guarded-reassociation-v1`, graph-position schema 6. See the single-job command below. [Release](reports/ALGO07/README.md) |
| ALGO07 qualified runtime composition | Supported production reference | Packages qualified numerical kernel substitutions under an integrity-checked worker manifest. The watcher accepts that release via `--worker-root`. [Build and replay](docs/operations/algo07-runtime-release.md) |
| ALGO07* | Research parity reference | One coordinator runs the ALGO02–07 stages against a private replay root. Use `python tools/run_algo07_star.py --root "$REPLAY_ROOT" --runtimes "$RUNTIMES" --manifest "$MANIFEST" --through ALGO07 --output "$OUT"`. [Coordinator and input preparation](docs/operations/algo07-star-plan.md) |
| algo07v3 | Supported standalone reference | Runs consolidated GLRT-to-publication inference with both calibration arms and eight figures. Run `.venv/bin/leo-algo07v3 run --request "$REQUEST" --work-dir "$work/v3" --timeout 1200`. Its `resume` command supports publication recovery. [Request format](docs/operations/algo07v3-cli.md) |
| algo07v4 | Supported full-budget native reference | Preserves the full numerical search budget using a pinned native backend. Build its manifest, then run the versioned request as shown below. [Release and verification](docs/analysis/algo07v4-release.md) |
| algo07v5 standalone | Active policy and accuracy evaluation | Reuses eligible initial controls and supports explicit policies for annotation training, inclusion, scheduling and recovery. Use its own native manifest and v5 request. The four named repair roles above also have a frozen replay driver. [Evaluation guide](docs/how-to/evaluate-algo07.md) |

On a source checkout `uv sync --locked` builds the packaged native extensions. Build the native manifest at its final path and bind it in the request. Substitute `leo-algo07v4` and a v4 request for the full-budget reference.

```sh
.venv/bin/leo-algo07v5 build-native --output "$work/v5-native"
.venv/bin/leo-algo07v5 run --request "$REQUEST" --work-dir "$work/v5-job" \
  --native-manifest "$work/v5-native/manifest.json" --timeout 1200
```

## ALGO01–07 lineage

ALGO02 through ALGO07 are sequential stages in the production chain. Each recovery worker consumes the completed predecessor and records the candidate or fallback. ALGO01 is a frozen research predecessor. The version suffix on a graph-position **storage module** numbers that contract independently of the standalone `algo07v3/v4/v5` commands.

| Algorithm | Role | Input, operation and entry point |
|---|---|---|
| [ALGO01](reports/ALGO01/README.md) | Historical research reference | Fits receiver position to causal satellite tracks with refreshed orbit phase and quality-gated calibration. `.venv/bin/python reports/ALGO01/build_evidence.py --figures-only` rebuilds its evidence figures. The linked specification gives the staged scientific replay. |
| [ALGO02](reports/ALGO02/README.md) | Production foundation | Builds track families from native GLRT and a causal catalogue. Curved tracks calibrate the receiver and linear tracks add predictive support. Run `python -m leo.cli.fast_graph_position --bulk-root "$BULK_ROOT" --tle-root "$TLE_ROOT" --once`. |
| [ALGO03](reports/ALGO03/README.md) | Production stage | Adds predictive single or joint track recovery to the ALGO02 result. Worker module `leo.cli.fast_graph_position_v2`. |
| [ALGO04](reports/ALGO04/README.md) | Production stage | Retries numerically difficult candidates and checks that existing observation owners are preserved. Worker module `leo.cli.fast_graph_position_v3`. |
| [ALGO05](reports/ALGO05/README.md) | Production stage | Splits eligible tracks at timing gaps and tests fragments with a conditional satellite refresh. Worker module `leo.cli.fast_graph_position_v4`. |
| [ALGO06](reports/ALGO06/README.md) | Production stage | Searches causal TLE history for additional satellite families explaining still-unassigned fragments. Worker module `leo.cli.fast_graph_position_v5`. |
| [ALGO07](reports/ALGO07/README.md) | Production endpoint | Checks whether a whole satellite family should be reassigned and publishes the guarded endpoint. Worker module `leo.cli.fast_graph_position_v6`. |

For ALGO03–07 use the selected module, the ID of a completed predecessor job and a positive UTC cutoff in nanoseconds. Run on the qualified replay host with the appropriate bulk store and numerical release. This example runs the ALGO07 watcher once against an explicit ALGO06 job. [ALGO03 operational guide](docs/operations/algo03-production-promotion.md) · [ALGO07 worker](src/leo/cli/fast_graph_position_v6.py)

```sh
.venv/bin/python -m leo.cli.fast_graph_position_v6 --once --bulk-root "$BULK_ROOT" \
  --minimum-completed-utc-ns "$CUTOFF_NS" --source-job "$ALGO06_JOB_ID"
```

## Other supported position diagnostics and regional receivers

| Method | Status and inputs | How to run |
|---|---|---|
| Blind multi-region Doppler-shape grid | Research comparison. Scores anonymous Doppler tracks against caller-supplied tiles, challenges each winner on disjoint tracks and can withhold a fix. Includes correct-region-missing trials. [Study and input schema](reports/2026_11_18_blind_regional_receiver/README.md) | `python reports/2026_11_18_blind_regional_receiver/predict_one.py --observation "$OBS" --catalog "$TLE" --regions "$REGIONS"` or `python -m tools.pipeline_eval replay --panel transfer16 --role grid` |
| V16 Hard60/B7 regional position | Archived-scan diagnostic. A bounded regional search on saved GLRT products. The earlier baseline, T1AT and V16 fits have a separate replay guide. [Worker](src/leo/cli/regional_position.py) · [Earlier fit comparison](docs/operations/adaptive-three-position-methods-2026-10-06.md) | `python -m leo.cli.regional_position --bulk-root "$BULK_ROOT" --tle-root "$TLE_ROOT" "$SESSION_ID"` |
| Adaptive TLE position | Archived-scan diagnostic. Bounded best-first TLE candidate selection. [Worker](src/leo/cli/adaptive_tle_position.py) | `python -m leo.cli.adaptive_tle_position --session-id "$SESSION_ID" --bulk-root "$BULK_ROOT" --tle-root "$TLE_ROOT"` |
| Shared-q fast position | Standalone reference. Joint receiver and satellite nuisance inference on exported tracking inputs. [Worker](src/leo/cli/shared_fast_position.py) | `python -m leo.cli.shared_fast_position --input "$TRACKING_INPUT" --output "$OUT" --tle-root "$TLE_ROOT"` |
| Expanded Doppler, orbit-corrected, identity mixture | Three conditional diagnostics on saved tracks and reviewed candidate identities. Compare an expanded frequency-error model, orbit corrections and uncertain discrete associations. [Method contract](src/leo/contracts/position_methods.py) | `python -m leo.cli.scan_position_methods --session-id "$SESSION_ID" --bulk-root "$BULK_ROOT" --tle-root "$TLE_ROOT" --output-root "$OUT"` |
| Early embedded designs | Historical prototypes for streaming tracks, guided pilots, family consensus, packed orbit tables, stationary forecasts, geometry-selected coresets, Doppler differences, grid refinement, pass events and a coordinate network. The comparison script scores their submitted endpoints. [Designs and individual entry points](reports/2026_11_18_embedded_prototypes/README.md) | `python reports/2026_11_18_embedded_prototypes/compare.py` |

The [initial design study](reports/2026_11_18_embedded_study/embedded-position-study.html), [location-transfer tests](reports/2026_11_18_location_transfer/README.md) and [comparison with all four v5 roles](reports/2026_11_18_v5_blind_comparison/README.md) preserve the inputs, assumptions and comparisons behind these prototypes. The [direct receiver checkpoint](reports/2026_11_20_direct_receiver_checkpoint/README.md) preserves work in progress on the detector, geometry and receiver clock. The [Standard analysis](docs/pipelines/standard-analysis.md) and [Research analysis](docs/pipelines/research-analysis.md) guides cover acquisition, pilot detection, tracking and other signal products.

## Registered benchmark experiments

Each name below is accepted by `python -m tools.pipeline_eval run --variant NAME`. **Compact v5 is the active position candidate.** The other entries are experimental alternatives, controls or individual pipeline stages. Some emit detector or timing evidence only. Use the roster for that study when reproducing a published result. The live `list` command prints the registry and available panels. [Benchmark commands and input requirements](tools/pipeline_eval/README.md) · [Per-experiment evidence](reports/2026_11_19_position_atlas/README.md)

<details>
<summary>Benchmark IDs and the change each one makes</summary>

| Variant ID | Operation |
|---|---|
<!-- receiver-variant-rows -->
| `iq_stream` | Read and decode IQ in bounded blocks |
| `glrt_batch` | Batch the full pilot correlation bank |
| `glrt_cascade` | Screen GLRT cells before the contrast calculation |
| `track_link` | Link native detections using bounded causal state |
| `track_reduce` | Compress track points before position search |
| `orbit_interp` | Reuse orbital states across region searches |
| `shape_score` | Screen below-horizon orbits before full interpolation |
| `v5_lean` | Compute original v5 coordinates without rendering evidence |
| `v5_core` | Run the reduced v5 branch selection, paired fits and cavity decision |
| `v5_one_seed` | Refine one neutral center assignment before the paired v5 cavity fit |
| `v5_first_ranked` | Refine only the first cold-ranked assignment in the v5 cavity fit |
| `v5_shared_search` | Reuse center projections and compact repeated v5 association work |
| `v5_two_refresh` | Limit early compact-v5 fits to two orbit phase refreshes |
| `v5_likelihood_reuse` | Reuse exact native likelihood terms at fitted v5 endpoints |
| `v5_secant_fit` | Use bounded secant steps in the compact v5 position solver |
| `interleaved_visits` | Skip one in four visits per RF channel before the compact fit (opt-in) |
| `v5_orbit_domain` | Extend causal orbit support for compact v5 corner projections |
| `v5_previous_orbit` | Isolate decayed previous elements in compact v5 priors (opt-in) |
| `v5_causal_orbit_fit` | Run compact v5 with three guarded numerical repairs (opt-in) |
| `v5_failed_only` | Retry only three diagnosed failures after unchanged compact v5 (opt-in) |
| `v5_stable_phase` | Stop orbital updates once receiver position and satellite timings settle |
| `v5_secant_two_refresh` | Combine bounded secant fitting with two early orbit phase refreshes |
| `v5_screen_winner` | Screen initial compact-v5 assignments and finish the winner |
| `v5_screen_secant` | Screen initial compact-v5 assignments using bounded secant fitting |
| `v5_armijo_fit` | Use an Armijo search for compact v5 position fitting |
| `v5_armijo_tail` | Check a coarse Armijo stop with two symmetric linearizations |
| `v5_armijo_finish` | Run Armijo fitting through the final compact v5 selection |
| `v5_armijo_aligned_finish` | Align the ordered Armijo phase seed before final reassociation |
| `v5_pruned_finish` | Check residual-fold and family support before final compact v5 searches |
| `v5_stream_recovery` | Bound resident orbital geometry in late compact v5 recovery |
| `v5_screened_pruned_finish` | Screen the initial assignment and prune the aligned v5 finish |
| `v5_lazy_pair` | Defer paired fit work on rejected compact v5 proposals |
| `v5_discovery_memory` | Reuse the repeated discovery association before the secant cavity fit |
| `v5_sparse_discovery` | Keep sparse early nomination diagnostics through the compact v5 finish |
| `v5_compact_memory_combined` | Use sparse discovery and sampled family widths in compact v5 |
| `v5_signed_context_memory` | Sample family and signed-context widths in compact v5 |
| `v5_nomination_memory` | Bound compact v5 family-cavity nomination memory |
| `v5_recovery_cache_memory` | Bound dirty orbit scratch cache in the compact v5 finish |
| `v5_recovery_reads` | Read late compact v5 orbital scratch in row order (opt-in) |
| `projected_fit` | Fit position after profiling per-track offsets |
| `shared_doppler` | Fit position with shared receiver clocks and satellite time shifts |
| `anchor_receiver` | Replay 16 IQ windows with the optimized historical detector and refit v5 |
| `glrt_odd_channels` | Use all visits to odd RF channels before tracking and v5 positioning |
| `glrt_even_channels` | Use all visits to even RF channels before tracking and v5 positioning |
| `orbit_projector` | Project Doppler and its phase derivative from orbit knots in one loop |
| `compact_finish` | Continue the compact cavity worker through frozen baseline adoption |
| `v5_recovery_bank_reuse` | Reuse immutable residual orbital geometry in final compact v5 |
| `v5_batched_salvage` | Bound the Gaussian score batches in v5 conservative recovery |
| `v5_catalogue_memory` | Batch catalogue propagation and retain fresh residual orbit arrays |
| `v5_stream_prepare` | Read native GLRT records incrementally ahead of the compact v5 finish |
| `catalogue_checksum` | Validate causal orbital element checksums with a byte lookup in v5 |
| `arc_validation` | Assign orbits on early track samples and verify them on later samples |
| `sweep_schedule` | Use alternate complete eight-channel sweeps before tracking and fitting |
| `iq_position` | Localize from newly computed GLRT detections in archived IQ |
| `point_votes_global` | Vote globally from GLRT point pairs and causal TLE |
| `point_votes_matched_tile` | Vote from GLRT point pairs within the original search tile |
| `rate_triplets_global` | Search globally from GLRT frequency triplets and causal TLE |
| `rate_triplets_matched_tile` | Search from GLRT frequency triplets within the original tile |
| `pass_geometry_global` | Infer two candidate sites per pass from measured Doppler curvature |
| `pass_geometry_matched_tile` | Fit pass geometry and receiver position on the original tile |
| `joint_pass_id_matched_tile` | Fit joint pass identities from GLRT on the original tile |
| `region_challenge_matched_tile` | Challenge the original tile against its neighbors from GLRT |
| `folded_doppler_global` | Search globally by folding GLRT Doppler and causal TLE predictions |
| `folded_doppler_matched_tile` | Fold GLRT Doppler predictions within the original tile |
| `contiguous_prefix_180` | Fit compact v5 on the first 180 seconds of capture-era GLRT |
| `raw_robust` | Rebuild tracks from complete capture-era GLRT and fit robust EM |
| `periodic_anchor` | Mix complete GLRT archives using one capture-era sweep every 64 sweeps |
| `robust_orbit_fit` | Refine fixed anonymous track assignments with orbital range rate |
| `robust_support` | Check a one-tile anonymous-track fit against held samples |
| `joint_orbits` | Fit joint orbit assignments from anonymous tracks on one supplied tile |
| `portable_native_joint` | Run the standalone joint receiver on complete native factors |
| `portable_native_clock` | Run the standalone smooth-clock receiver on complete native factors |
| `deadline_30s` | Run compact v5 with a smooth-clock fallback within 30 seconds (opt-in) |
| `deadline_90s` | Run compact v5 with a smooth-clock fallback within 90 seconds (opt-in) |
| `deadline_180s` | Run compact v5 with a smooth-clock fallback within 180 seconds (opt-in) |
<!-- end-receiver-variant-rows -->

</details>
