# ALGO08v3 solver recovery and the remaining 2× budget

The orbit-support repair returned both calibration-arm fixes on the first two saved ALGO08v3 interpolation failures. DS30-0022 reproduced deployed ALGO08v2 exactly. DS30-0129 returned different satellite owners, with 1,079 fewer associated observations per arm and higher error in both arms. DS30-0129’s assignment divergence remains unexplained. [DS30-0022 receipt](measurements/algo08v3-DS30-0022-orbit-support-saved.json) · [DS30-0129 receipt](measurements/algo08v3-DS30-0129-orbit-support-saved.json)

## Orbit support

Both failed candidate traces entered the receiver-smooth corner retry and reached the sparse rank projection. The sparse projection installs `shifted` on the scan instance. That attribute takes precedence over the retry’s class-level `shifted` wrapper, so the call reached the nominal orbit bank again. Both deployed terminals reported `orbit_policy: orbit_support`. The fix wraps the active bound method on the scan instance and passes the same causal support extension through the sparse and stock projections. The corner, phase and derivative checks still govern eligibility for direct SGP4 propagation. [Repair](../../../tools/pipeline_eval/variants/v5_orbit_domain.py) · [Component test](../../../tests/pipeline_eval/test_v5_orbit_domain.py)

The saved trials use the unchanged frozen ALGO08v3 solver composition and apply this one repair in the trial process. Each candidate uses its original detector document, region and causal archive. Its detector rows exactly match the deployed control for both recordings. The CPU and wall clock cover saved detections through position and numerical evidence, including the retry. The deployed comparison uses the archived controls. The timed boundary excludes raw acquisition and figure rendering. Both trial processes share the Gauss lock with the DS30 panel and use pinned CPU 2, nice 15, best-effort I/O priority 7 and one numerical thread.

| Recording | Equal detector rows | Associated observations per arm, deployed → recovered | Owner digests agree | Added orbit knot | Recovered CPU / wall s |
|---|---:|---:|---|---:|---:|
| DS30-0022 | 10,536 | 2,388 → 2,388 | Both arms | −18 s | 34.329 / 38.848 |
| DS30-0129 | 13,504 | 4,059 → 2,980 | Neither arm | +318 s | 42.803 / 43.415 |

The horizontal errors use the frozen DS30 reference audit after inference. This comparison keeps the candidate and control observations and offered region matched and reports frequency fit and position error independently. [Position reference](../../2026_11_21_ds30_full/reference-audit.json)

| Recording | Calibration | RF RMS, deployed → recovered (Hz) | Horizontal error, deployed → recovered (km) | Endpoint movement |
|---|---|---:|---:|---:|
| DS30-0022 | Fixed zero | 161.7961 → 161.7961 | 1.2937 → 1.2937 | 0 m |
| DS30-0022 | Fitted | 161.6148 → 161.6148 | 1.3107 → 1.3107 | 0 m |
| DS30-0129 | Fixed zero | 108.5044 → 109.6572 | 0.6778 → 0.7261 | 180.53 m |
| DS30-0129 | Fitted | 108.5826 → 109.7195 | 0.6112 → 0.6894 | 153.10 m |

### Prospective check on DS30-0239

Pair 72 entered the archive after the guard and the first two results were committed. It failed in the same sparse projection during the frozen corner retry. One saved solve used the already committed guard `c23a7c89d`, the same shared CPU slot and all 13,418 original detector rows, which exactly matched the deployed rows. With one added knot at +318 s in two corner projections, the solve returned both fixes in 44.626 CPU s and 45.034 wall s. Both arm endpoints, RF RMS and owner digests matched ALGO08v2 exactly, with 4,339 associated observations per arm. The original panel receipt retains the solver failure and its archived SHA-256 `42b8fbefa2523d428ddc884362f3d8a0269b4612099c6cf64f5542be9d5c8eaf`. This check adds one prospectively observed failure from the same physical panel. [Saved trial receipt](measurements/algo08v3-DS30-0239-orbit-support-saved.json)

| Calibration | RF RMS, both builds (Hz) | Horizontal error, both builds (km) | Endpoint movement |
|---|---:|---:|---:|
| Fixed zero | 114.6647 | 0.4066 | 0 m |
| Fitted | 114.7558 | 0.5859 | 0 m |

### Final five-failure census

The completed 100-pair audit at `027acfc35` identified DS30-0234 and DS30-0247 at panel ranks 86 and 100. Both had failed in the same sparse corner retry and entered the archive after the guard was frozen. Each additional check ran once on its original saved detector document and causal TLE archive. The two cases had 13,266 and 13,140 detector rows, respectively, with exact equality to the corresponding ALGO08v2 rows. Both original failure receipts retain their final-audit file digests. [DS30-0234 saved trial](measurements/algo08v3-DS30-0234-orbit-support-saved.json) · [DS30-0247 saved trial](measurements/algo08v3-DS30-0247-orbit-support-saved.json)

| Recording | Recovered decision | Associated observations per arm, deployed → recovered | Owner digests agree | New orbit knots | Recovered CPU / wall s |
|---|---|---:|---|---:|---:|
| DS30-0234 | Both fixes | 3,495 → 3,495 | Both arms | −22 to −18 s | 34.239 / 34.763 |
| DS30-0247 | Both fixes | 3,410 → 3,307 | Neither arm | +319 to +323 s | 48.261 / 48.976 |

| Recording | Calibration | RF RMS, deployed → recovered (Hz) | Horizontal error, deployed → recovered (km) | Endpoint movement |
|---|---|---:|---:|---:|
| DS30-0234 | Fixed zero | 107.1329 → 107.1329 | 0.3437 → 0.3437 | 0 m |
| DS30-0234 | Fitted | 107.0486 → 107.0486 | 0.5311 → 0.5311 | 0 m |
| DS30-0247 | Fixed zero | 93.8289 → 94.3470 | 0.5658 → 0.6928 | 493.99 m |
| DS30-0247 | Fitted | 93.8492 → 94.3352 | 0.6669 → 0.7218 | 475.49 m |

The frozen guard recovered a fix in both calibration arms for all five saved failures. Three cases exactly reproduced ALGO08v2’s endpoints, RF RMS and ownership. DS30-0129 and DS30-0247 retained fewer associated observations and had higher horizontal errors in both arms. All five original candidate failures remain in the final 100-pair result. The recovery clocks cover saved detections through numerical evidence and provide no new raw-publication timing.

## Speed relative to ALGO08v3

In the first 56 archived pairs, the 54 candidate runs with terminals took 5,546.7 s in total across 3,714.8 s through detections, 1,678.1 s through solving and numerical evidence, and 153.8 s to exit. The two crashes contribute elapsed time to their fixed panel comparison. Their missing terminal timestamps leave them out of this stage split. Stage clocks come from the detection and terminal file modification times and the recorded launch-to-terminal and launch-to-exit durations. The zero-charged-input subset spans three recordings, with summed elapsed time split 49.70%, 46.65% and 3.65% across the same boundaries. [Stage clock calculation](compare_publications.py)

Reducing solve-and-evidence time by half yields a projected 1.18× summed elapsed speedup. Reducing both the first two stages by half leaves 51.39% of summed elapsed time and a median per-recording ratio of 51.34%. A 2.5× speedup through detections and approximately 1.48× through solve-and-evidence reaches the summed-wall target if publication time stays fixed. These are stage budget calculations on the existing panel prefix.

The next solver test can batch the two existing finite-difference evaluations at each curvature refresh. The two trial sites share the current position model’s immutable observation layout, priors, noise inputs and orbit phase reference. In the native kernel, SIMD lanes across sites can preserve each site’s own original arithmetic sequence, cold Gamma-precision updates, cap and conditioning decisions. Independently continue a lane at its own stopping count and use the scalar path on unsupported or poorly occupied batches. Evaluate output fidelity on the same batches before timing a complete saved solve. The older dense DS30-0008 profile has 376 such probes at 188 refreshes for 11.876 CPU s. The separate exact evidence grid has an additional 6.893 CPU s and could use site batching with the same per-site rules. These are profiled costs before a batch implementation. Warm starts, changes to the robust-update sequence and approximate temporal trust have already shown scientific differences or small measured savings. [Fit profile](solver-fit-dependency-audit.md) · [Robust updates](solver-robust-updates.md) · [Temporal trust](solver-temporal-trust.md)

## Reproduce a saved-packet check

Run [the verification script](solver_orbit_support_trial.py) from this branch. Supply the frozen bundle, one archived case’s `pair.json`, and a fresh output path. The paired receipts supply the original region and archive. The runner verifies their contents, the frozen source pins, both saved acquisition documents and the deployed terminal. `--verify-only` stops after these input checks.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
frozen="$bench/integration-exact-curved-lookahead"
packets=/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications
new_receipt=/var/tmp/algo08v3-DS30-0022-orbit-support.json

flock -w 600 "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$frozen:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 \
  timeout 130 "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/solver_orbit_support_trial.py \
  "$frozen" "$packets/DS30-0022/pair.json" "$new_receipt"
```

The DS30-0022 and DS30-0129 receipts predate extraction of the portable runner. The same frozen launcher and injected guard supplied those results. The report records 52 passing component and adjacent integration tests for the guard.
