# DS2 September 24 successor-corpus rerun plan

## Decision

The current DS2 evidence is internally consistent for the sealed 20-capture corpus. A true rerun is required only if corpus membership changes. The two same-day exclusions are `scan-fw-294be7850b76a34d` and `scan-fw-ff02a0ba4200d0dc`; both currently lack analysis status and a V14 receipt. Their appearance in a new inventory is not enough to admit them. Before starting a 22-capture successor, each needs a completed V14 product, sealed receipt, eligible capture metadata, and receipt-bound causal cache.

The proposed inventory describes the same 20 sessions as the final manifest. Its V14 counts (441 tracklets and 12,694 observations) agree with the DS1/DS2 final comparison. The portable report's 503 qualified tracks and 13,111 observations are fitting counts, not different capture membership.

No existing report should be overwritten. A successor uses a new directory such as `reports/2026_09_24_ds2_sep24_rerun_22/`, a new external cache root, and a new final comparison. Do not relabel old 20-capture development evidence as a 22-capture result.

## Verified source bindings

All local SHA-256 sidecars for the final manifest, portable dataset/evaluation/execution/refinement indexes, missing-model artifacts, consistent-rate artifacts, and the two geometry inference artifacts match their bytes (15/15). All six source digests recorded by `2026_09_24_ds1_ds2_final_comparison/summary.json` also match their referenced files (6/6).

| Source | SHA-256 |
| --- | --- |
| New read-only inventory | `87edfc7fe900fb4639c8e793d0be574e4fd26a5ab9d0bbff0a3d4a8527c9096e` |
| Existing 20-capture final manifest | `6f93ed1b87cbd4149b038cadec197c1be8017a398912052f251b1cd9c13bba8a` |
| Registry | `cf7817cdbb097ecd86d307b499e455b67b341f163b12ef6ab5a0ba20682faf2f` |
| Portable registry accounting | `5efe02cd0879cf399db059ae3942f45d3fbc60d3708c0d026deb24f8de5ffea9` |
| Existing final comparison | `add7f657661b907a611e94d474391ea611e17ad31bac8f048888e044a6d44ee4` |

The portable dataset binds that final-manifest digest and lists all 20 IDs. The cap-800 manifest and missing-model plan independently list the same 20 IDs. The geometry package is a valid three-session conditional subset: `f3ce5fe73aa40506`, `9f3d5067d149118e`, and `cfcf667726e80735`.

## Registry disposition

“All-20 complete” means the saved inference consumed all 20 whole sessions. “Three-session subset” means the model ran only on the three geometry-authorized members of that same corpus. A change from 20 to 22 invalidates every all-20 objective, finalist, exact gate, and post-seal comparison. The legacy arm remains deliberately rejected.

| Registry model | Existing DS2 evidence | Coverage | Action if the two missing captures become eligible |
| --- | --- | --- | --- |
| `baseline_doppler` | complete | All 20 | True wide-prior rerun |
| `shared_global_receive_time` | complete | All 20 | True wide-prior rerun |
| `regularized_per_scan_time` | complete | All 20 | True wide-prior rerun |
| `independent_per_track_time` | diagnostic complete | All 20 | True rerun if retaining the diagnostic |
| `causal_per_norad_orbit_rate` | complete | All 20 | True wide-prior rerun and exact gate |
| `rate_aware_joint_geographic_screen` | bounded local complete | All 20 | Rebuild from the new parent; rerun local screen and gate |
| `soft_identity_mixture` | diagnostic complete | All 20 | True rerun if retaining the diagnostic |
| `equal_weight_joint_multiscan_position` | complete | All 20 | True wide-prior rerun |
| `consistent_cap800_joint_objective` | bounded local complete | All 20 | Rebuild from the new parent; rerun proposal and exact gates |
| `shared_norad_rate_joint` | complete, zero overlap | All 20 | Recompute support; the zero-overlap conclusion cannot be reused |
| `regularized_common_plus_session_scale` | complete, unqualified | All 20 | Rerun only as the same unqualified diagnostic after new rate finalists seal |
| `learned_pointing_cone_quantiles` | geometry diagnostic complete | Three-session subset | Do not rerun without a new explicit geometry binding |
| `fixed_hard_cone_orientation` | geometry diagnostic complete | Three-session subset | Do not rerun without a new explicit geometry binding |
| `staged_full_fov_cone_sweep` | geometry diagnostic complete | Three-session subset | Do not rerun without a new explicit geometry binding |
| `local_fitted_full_fov_cone_position` | geometry diagnostic complete | Three-session subset | Do not rerun without a new explicit geometry binding |
| `robust_residual_likelihood_rerank` | diagnostic complete | All 20 | Rerun after new coarse/refined/fine rate finalists seal |
| `legacy_joint_session_scale_lbfgsb` | rejected, not rerun | None | Do not run; repaired block-coordinate is its replacement |

Twelve registry models have concrete all-20 DS2 computations (seven portable-wide arms, three bounded/follow-up arms, shared-NORAD overlap accounting, and residual rerank). Four cone arms are complete only on the authorized three-capture slice. Sixteen models have DS2 evidence; the seventeenth is explicitly rejected rather than missing.

## Bounded execution DAG

```text
V14 receipts + causal caches for both excluded sessions
        |
        v
fresh 22-session manifest and randomized whole-session partition
        |
        +----------------------> conditional geometry admission check
        |                                |
        v                                +--> cone branch only with a new explicit binding
portable 22-session wide-prior run
        |
        v
coarse -> reference-free refinement -> fine refinement -> exact gates
        |
        +------------------------------+-------------------------------+
        |                              |                               |
        v                              v                               v
cap-800 / rate-aware local       session-scale + residual          shared-NORAD overlap
screen (2 workers)               diagnostic (2 workers)            accounting
        |                              |                               |
        +------------------------------+-------------------------------+
                                       |
                                       v
                         post-seal evaluation and successor comparison
```

Do not run the current DS2 scripts directly for this successor. The portable builder explicitly rejects any corpus whose size is not 20, and `execute.py`, `refine_joint.py`, and `refine_joint_fine.py` write indexes in their current report directory. First implement a fresh parameterized successor driver accepting a manifest path, output root, and `joint-all<N>` task prefix. It must retain whole sessions, a seeded randomized outer partition, receipt-bound caches, reference-free inference, and post-seal-only evaluation.

After that driver is reviewed, its bounded invocation contract is:

```bash
RUN_ROOT=reports/2026_09_24_ds2_sep24_rerun_22
CACHE_ROOT=/var/tmp/leo-ds2-sep24-rerun-22-cache
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

# Gate A: only after both formerly missing sessions pass admission.
.venv/bin/python "$RUN_ROOT/build_manifest.py" --sessions 22 --output "$RUN_ROOT/manifest.json"
.venv/bin/python "$RUN_ROOT/build_portable_plan.py" --manifest "$RUN_ROOT/manifest.json" --cache-root "$CACHE_ROOT" --output "$RUN_ROOT/portable"

# Gate B: at most four workers; the driver serializes memory-heavy joint jobs.
timeout 7200 .venv/bin/python "$RUN_ROOT/run_portable.py" --plan "$RUN_ROOT/portable/plan.json" --cache-root "$CACHE_ROOT" --workers 4
timeout 3600 .venv/bin/python "$RUN_ROOT/refine_joint.py" --plan "$RUN_ROOT/portable/plan.json" --cache-root "$CACHE_ROOT" --workers 3
timeout 3600 .venv/bin/python "$RUN_ROOT/refine_joint_fine.py" --plan "$RUN_ROOT/portable/plan.json" --cache-root "$CACHE_ROOT" --workers 3

# Gate C: run these together, retaining a four-worker combined ceiling.
timeout 1800 .venv/bin/python "$RUN_ROOT/run_consistent_rate.py" --plan "$RUN_ROOT/portable/plan.json" --cache-root "$CACHE_ROOT" --workers 2 &
timeout 1800 .venv/bin/python "$RUN_ROOT/run_missing_models.py" --plan "$RUN_ROOT/portable/plan.json" --cache-root "$CACHE_ROOT" --workers 2 &
wait
.venv/bin/python "$RUN_ROOT/account_shared_norad.py" --plan "$RUN_ROOT/portable/plan.json"

# Gate D: only sealed inference may reach the reference coordinate.
.venv/bin/python "$RUN_ROOT/evaluate_postseal.py" --input-root "$RUN_ROOT" --output "$RUN_ROOT/evaluation.json"
.venv/bin/python "$RUN_ROOT/build_final_comparison.py" --ds2-root "$RUN_ROOT" --output "$RUN_ROOT/final-comparison.json"
```

The geometry branch is intentionally absent from the default commands. If an excluded session later acquires an explicit LT3D-001A binding, use a fresh geometry export and blind re-associated cone run in `RUN_ROOT` with both RX-to-slot mappings; otherwise retain the three-capture subset.

## Runtime basis and limits

The logged 20-session portable artifacts used about 1,782 single-task CPU seconds, 3,838 seconds of serialized joint work, and 2,121 seconds of three-worker fine refinement: about 83 minutes of observed four-worker wall-clock work before plan/cache creation. A 22-session run is expected to take roughly 90–105 minutes for Gate B; the two-hour timeout is a hard stop, not an expected duration. Cache construction and V14 backfill are admission gates with no historical runtime recorded here and are excluded from this estimate.

Recorded follow-up times are 431 seconds for cap-800 (two workers), 78 seconds for missing models (four workers), and 181 seconds for the current three-session blind cone sweep. With Gate C capped at four combined workers, budget 10–15 minutes after the portable parent seals. Post-seal evaluation, digest verification, and comparison building should be under five minutes. The optional cone branch is about four minutes for the present three-session scope and must be re-estimated for new geometry-authorized inputs.
