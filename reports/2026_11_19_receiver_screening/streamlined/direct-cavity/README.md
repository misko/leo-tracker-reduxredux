# Direct compact v5 cavity

The staged direct entry reproduced all eight compact secant positions and conditional Doppler RMS values exactly across four fresh same-input pairs. It preserves the same initial search, paired conservative fitting, signed history and cavity choice. DS26-0036 opened the cavity gate, and the other three retained their signed incumbent. All eight scheduled workers completed. [Both-arm position charts](charts/index.html) · [Source and input lock](source-lock.json) · [Parity](parity.json)

## Explicit entry

`tools.pipeline_eval.variants.v5_direct_cavity.run` takes stored native GLRT, its declared session and SHA-256, a track configuration and its SHA-256, a read-only causal TLE archive, an offered tile and broad screen, and the two compiled numerical libraries. `solve` also accepts an already decoded native document and caller-supplied archive and numerical bound. Use the direct entry in a numerical process dedicated to this solve. It returns both `c = 0` and fitted-`c` positions, conditional RMS, and the selected frequency objective when emitted by the scientific stage.

The source payload packages checked bytes from the immutable project science release and eight workspace paths. The measurement launched from this staged tree with the source archive and evaluator omitted from its import path. It reads native and track-config bytes once, uses the snapshot reader's digest checks, and emits one result. No runner or evaluator request is needed by the direct CLI. All four direct runs used a native bound rebuilt from staged C source with the same compiler policy and a binary SHA-256 identical to the qualified original. The staged payload contains the complete frozen source distribution so the dated scientific call paths remain available. It contains no recordings, catalogue inputs, host-specific build manifests, or evaluator runner. [Source payload](compact-cavity-source.tar.gz) · [Per-file and native binary hashes](bundle.json) · [Published artifact digests](receipt.json)

The direct worker reuses the existing compact projector and core ranking/initial-fit helpers. Those modules still contain historical entry points. Their evaluation launcher code is dormant under the direct entry. The optimizer is the exact five-refresh secant numerical body maintained separately from its frozen instrumented wrapper. Six temporary function bindings attach the orbit projector and optimizer to the existing frozen call sites. The worker releases its nominal signed-phase problem immediately after leave-family-out nomination, including before an offered joint fit. There are no direct-runtime source overlays. The retained native-bound adapter still generates its validation and result code from the frozen hierarchical function at import. The scientific geometry and family algorithms are from the archived project release, whose `localization_v3` and `localization_v4` implementations are absent from the currently maintained `src/leo` tree.

## Paired results

The ordinary inputs use complete native factors derived from stored whole recordings. The capture-era control is DS26-0026. DS26-0076 is the held capture selected by the predeclared salt from 49 eligible archive successes after excluding the prior four and both ordinary captures. Both methods consumed identical scientific requests and ran on the same CPU for each capture. The native-to-cavity launcher times include projector compilation and result output. The staged native bound is built once before all measurements, matching the prior launcher's use of its prebuilt bound. [Protocol](PROTOCOL.md) · [Per-stage and whole-launcher timings](timings.csv)

| Input | Role | CPU | Control wall s | Direct wall s | Control CPU s | Direct CPU s | Control peak child MiB | Direct peak child MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DS26-0036 | Ordinary | 4 | 51.80 | 59.86 | 47.71 | 46.32 | 1031.91 | 993.00 |
| DS29-0082 | Ordinary | 5 | 47.76 | 40.24 | 36.71 | 37.09 | 893.50 | 885.70 |
| DS26-0026 | Capture-era control | 6 | 54.90 | 71.58 | 50.73 | 47.34 | 1238.88 | 1238.88 |
| DS26-0076 | Held capture-era | 4 | 75.42 | 52.66 | 48.20 | 46.48 | 1107.75 | 1107.75 |

Timing varied by recording on the shared host. The direct worker took 3.40 fewer CPU seconds on the largest improvement and 0.38 more seconds on DS29-0082. Its peak child RSS fell by 38.91 and 7.80 MiB on the ordinary pair and was unchanged on the capture-era pair. The normal output has no stage traces, slope diagnostic, per-iteration instrumentation, native process receipts, or evaluation archive side effects. Common observation, track, initial-branch, and projection counts matched.

Each entry below is shared by the control and direct worker. Geographic errors use the held roof reference. Conditional RF fit is a separate quantity and moved in both directions with fitted `c` across the four recordings. The original control output includes conditional RMS but omits frequency objectives. The direct objectives are in the per-arm CSV. [Per-arm scores](scores.csv)

| Input | `c = 0` error km | Fitted `c` error km | `c = 0` RMS Hz | Fitted `c` RMS Hz |
|---|---:|---:|---:|---:|
| DS26-0036 | 0.218118 | 0.180112 | 102.253327 | 102.288908 |
| DS29-0082 | 2.789469 | 2.654183 | 106.672251 | 106.588481 |
| DS26-0026 | 1.622195 | 1.550894 | 72.218233 | 72.084333 |
| DS26-0076 | 2.250529 | 2.220709 | 53.732760 | 53.733751 |

## Code reach

Separate first-visit line tracing used the ordinary DS29-0082 input on CPU 5. The direct worker reached 272 paths and 27,884 file/line pairs. The control reached 280 paths and 28,421 pairs. The runner’s two evaluation imports and the benchmark CLI import occurred only in the control. Both runs reached 84 generated line locations in the native bound. The trace counts include import-time execution and exclude the diagnostic itself, Python’s standard library, and third-party packages. Both traced endpoints and their conditional RMS matched the corresponding ordinary runs. The selected conditional frequency objectives also matched exactly at 11,815.163224720734 and 11,818.344654360739. The traced control took 60.58 seconds wall and 39.24 CPU seconds, and the traced direct run took 69.22 wall and 41.20 CPU seconds. These diagnostics timed the launched worker after compilation and were run separately from the release timings. [Executed lines and objective trace](trace-summary.json) · [Compressed path inventory](trace-lines.json.gz)

## Run the unpacked source payload

Use Python 3.12, the compatible scientific environment, and `cc` on a Linux host. The measured environment used NumPy 2.5.2, SciPy 1.18.1 with the single-thread LP64 OpenBLAS provider and SGP4 2.27. Extract the source into a fresh local directory and work from its root. Keep the input catalogue in the standard read-only archive layout.

The unmodified frozen distribution in the payload includes three prebuilt Linux x86-64 CPython 3.12 extensions, `_joint_lu`, `_regional_orbits`, and `_native_acquisition`. The traced ordinary run imported `_native_acquisition` through the acquisition module without reaching its detector kernel calls. It did not reach the `_joint_lu` loader or `_regional_orbits` caller. The compact projector and native bound were the separately compiled kernels used by these direct inference measurements. Deployment was qualified on the measured x86-64 Linux environment.

```sh
export PYTHONPATH="$PWD"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1
python -B - <<'PY'
from pathlib import Path
from leo.analysis.localization_v4.backend import build_native
from tools.pipeline_eval.variants.orbit_projector import compile_kernel

build_native("native")
compile_kernel(Path("orbit_projector.so"))
PY
python -B -m tools.pipeline_eval.variants.v5_direct_cavity \
  --native "$native_glrt" --native-sha256 "$native_sha256" --session "$session_id" \
  --track-config "$track_config" --config-sha256 "$config_sha256" \
  --archive "$causal_tle_root" --native-backend native/manifest.json \
  --library orbit_projector.so --tile "$tile_lat" "$tile_lon" \
  --screen-center "$screen_lat" "$screen_lon" --width-km 25
```
