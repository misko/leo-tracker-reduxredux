# Direct robust likelihood design assembly

Direct matrix assembly and selected-row scaling saved **2.52 CPU seconds** in one complete DS30-0008 saved solve. Both calibration arms reproduced deployed coordinates and RMS exactly. Elapsed time rose by **0.75 seconds** in that pair. The southern control reproduced its deployed outputs with **0.05 seconds** less CPU. [Paired receipt](measurements/solver-curved-design.json)

The released robust solver builds separate dense hardware, receiver, phase, orbital and curve blocks, concatenates them, scales the full design, then selects the observations for the current fit. This trial writes the same columns into one fresh C-order matrix. Normal and history likelihoods select the original rows and multiply that private dense selection by the same original scales. [Overlay](../../../tools/pipeline_eval/variants/algo08_curved_design.py)

## Work covered

The archived dense profile spent 1.187 CPU seconds in `column_stack` from `JointMarginal.calculate`, of 1.470 seconds for all `column_stack` calls. `JointMarginal.calculate` itself used 1.161 exclusive seconds and the history closure used 2.701 exclusive seconds. The corresponding earlier portable southern timings were 0.490, 0.717 and 0.802 seconds. Those method totals include work such as fixed arithmetic and posterior readouts that the overlay leaves in place. Dense native or fallback likelihood consumed 14.099 and 5.120 inclusive seconds respectively, with port validation using 0.781 seconds. These profiles precede the margin crossover and use a different southern simulation from the direct comparison below. [Dense profile](restored-scout-0008-solver-profile.md) · [Portable southern profile](screened-stock-profile.md)

The direct assembly reads the current hardware, receiver basis, aliases as resolved in the model, phase derivatives and scales, orbital modes, family labels and curve constants. For a model with distinct supported families, each row has at most one three-column orbital slot. The direct scatter uses the same two elementwise multiplications as the released per-family loop. Receiver scaling still uses two sequential multiplications. The direct selector uses the current keep mask and multiplies the result in place, leaving the published all-row design independently owned. The change keeps the same row and column order, input validation, reduction and factorization order, posterior export, trial points and search decisions. Non-eligible assembly contexts execute the source-pinned released block. [Released design](../../../src/leo/analysis/localization_v3/marginal.py) · [History likelihood](../../../src/leo/analysis/localization_v3/history_position.py)

The instrumentation times design assembly and selection separately from the orbit projection, dynamic response and conditional residual, validation, native structured likelihood, dense fallback, and predictive reconstruction. This covers ordinary curved likelihood calls during both fitting and evidence generation. Earlier predictive scratch work targeted the supplemental prediction model. Prior fixed Gram and complete-call caching act inside or at the entrance of the backend and can retain their existing behavior. [Predictive layout](solver-predictive-layout.md) · [Fixed Gram](solver-fixed-gram.md) · [Exact call cache](solver-exact-likelihood-reuse.md)

## Saved-input check

The runner uses the archived `977e…` dense physical solve and `4457…` public southern containing solve from the deployed-margin crossover. It verifies both saved detector documents, the archive and offer, frozen source pins and the original crossover terminal. Each measured process restores only the same original margins at noise estimation. The solver clock includes complete saved-detection preparation and the final numerical evidence packet, following the existing harness. It excludes detector execution and publication rendering. The instrumented stock and direct paths run as separate processes under the Gauss lock on CPU 2. The physical control runs first and the southern direct variant runs first. [Crossover source and receipt](solver-deployed-margin-recovery.md) · [Runner](solver_curved_design_trial.py)

| Boundary | Dense calls | Dense stock → direct CPU (s) | Southern calls | Southern stock → direct CPU (s) |
|---|---:|---:|---:|---:|
| Full feature assembly | 1,466 | 2.613 → 1.665 | 731 | 0.0545 → 0.0444 |
| History masked scaling | 1,022 | 2.092 → 0.931 | 565 | 0.0118 → 0.0097 |
| Normal masked scaling | 428 | 0.597 → 0.459 | 150 | 0.0025 → 0.0023 |
| Total targeted CPU | | 5.302 → 3.056 | | 0.0688 → 0.0564 |
| Complete saved solver CPU | | 56.160 → 53.637 | | 4.473 → 4.428 |
| Complete saved solver elapsed | | 57.028 → 57.783 | | 4.554 → 4.498 |

The dense preparation saving was 2.247 CPU seconds across the three measured blocks. Even eliminating the original 5.302-second cost would save about 9.4% of the saved-solver CPU with the rest fixed. The later direct replay preserved both arm paths, all 4,472 owners per arm, both endpoint objective replays, all 179 numerical grid points and their scores, and the endpoint reuse and posterior handoff counts. Its RF RMS remains 129.703 Hz fixed-zero and 129.663 Hz fitted. The off-site replay preserved the same fields and 266 owners per arm, with RMS 6.502 and 6.392 Hz. All four endpoints differ from deployment by exactly 0 km. The dense frozen grid retains the known pre-existing margin-control score differences from deployment of at most `7.276e-12` per arm. The southern grid stays exact against deployment. The whole-solver clocks use one pair per workload and give no established elapsed-time saving. [Exact coordinates and packet digests](measurements/solver-curved-design.json) · [Deployment grid comparison](measurements/solver-deployed-margin-recovery.json)

An initial southern run and the measured dense stock control passed every scientific comparison but compared an incidental endpoint or posterior CPU counter against the older archived run. The final runner compares the backend counts and treatment while ignoring timing fields. The dense stock measurements are carried forward with that same read-only comparison applied to the saved receipt. No additional dense control was needed.

Six component tests cover both calibration widths, current values and supported slots, released fallback for duplicate slots, independent result ownership, trimmed and untrimmed masks, the two original scale vectors, signed zero and subnormal values. [Component tests](../../../tests/pipeline_eval/test_algo08_curved_design.py)

## Frozen selected-score successor

The opt-in successor has specification `sha256:e2180d3217abf8841c4799e8aeb3b758d43a8965a1e6e6e3bcf5c463b7da247a` in `/tmp/leo-algo08v2-2x-bench/integration-fractional-selected-curved-design/spec.json`. It inherits the selected-exact fractional receiver from `e819d4…`, the supplied-offer screening policy, wrapped longitude, terminal regional veto and both calibration arms. The freezer verifies the parent source and binary manifests, the original physical and southern saved comparisons, and the three installed solver sources used by the measured overlay. The receiver and native libraries retain their original digests. A complete file comparison permits changes only to the manifest, experimental launcher and measured overlay. [Successor manifest](measurements/fractional-selected-curved-design-freeze.json) · [Parent manifest](measurements/fractional-absolute-selected-v3-freeze.json)

`curved_design: true` scopes the measured assembly to the solver callback after the launcher sets its other hooks. Enabled runs report assembly and masked-selection counts. Earlier bundles omit the option and retain their original behavior. The freeze and four integration component tests check provenance, runtime module origin, scope and library relocation. The saved-solver comparisons above supply the numerical timing for the overlay. This successor has yet to run a paired raw publication. [Freezer](freeze_curved_design.py) · [Integration tests](../../../tests/pipeline_eval/test_freeze_curved_design.py)

## Reproduction

Use `case=DS30-0008` with `freeze=integration-frame-plane-terminal-veto`, or `case=south` with `freeze=integration-spectral-vectors-wrapped-longitude`. Run each mode once, in the order stated above. Output paths must be fresh.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$bench/$freeze:$release/src:$release" \
  timeout 89 "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/solver_curved_design_trial.py "$case" "$mode" \
  "$bench/deployed-margin-saved-cross/$case" "$bench/$freeze/spec.json" "$output"
```

To reproduce this earlier bundle from a newer checkout, give the freezer the launcher bytes from `81ce543a5` or from the earlier verified bundle. Give it fresh bundle and receipt paths. The destination path enters its specification digest.

```sh
PYTHONPATH=src:. python -BPs -m reports.ALGO08.single-core-2x.freeze_curved_design \
  "$bench/integration-fractional-absolute-selected-v3" "$new_bundle" "$new_receipt" \
  --launcher-source "$old_launcher_source"
```
