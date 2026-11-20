# Standalone lifetime-bounded compact v5 cavity

The standalone direct receiver returned both calibration arms on **both** ordinary recordings in Linux services capped at 512 MiB with zero swap. Its four coordinates and conditional Doppler RMS values match the earlier unrestricted direct, unrestricted compact secant, and capped lifetime-cavity controls exactly. Its selected frequency objectives match the unrestricted direct run in all four arms. The previous direct worker and its parser-only continuation both returned zero positions on these inputs. [Both-arm charts](charts/index.html) · [Scientific parity](parity.json) · [Prior failed cap attempts](../../streamlined/direct-cavity-cap/README.md)

| Stored input | Pin | Capped wall s | Service CPU s | Peak cgroup MiB | Peak process RSS MiB | `c = 0` error km / RMS Hz | Fitted `c` error km / RMS Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 4 | 50.07 | 49.197 | 404.35 | 454.24 | 0.218118 / 102.253327 | 0.180112 / 102.288908 |
| DS29-0082 | 5 | 35.57 | 34.737 | 400.57 | 445.87 | 2.789469 / 106.672251 | 2.654183 / 106.588481 |

Each service verified its actual pin, 536,870,912-byte memory limit, zero swap, and nice 10 inside the numerical process. Both used one numerical thread and an independent user cgroup with a 165-second limit. Neither recorded an OOM kill. The workers ran concurrently on separate CPU cores. Supervisor wall includes service startup and teardown. CPU is the systemd service total. Cgroup high-water marks are exact byte values sampled at numerical exit and are distinct from process RSS. The separate raw systemd log confirms the rounded service peak. Both workers use an explicit disk `TMPDIR` in local scratch. [Resource measurements](resources.csv) · [All cap samples and results](positions.jsonl.gz) · [DS26 service log](DS26-0036-service.log.gz) · [DS29 service log](DS29-0082-service.log.gz)

## Numerical integration

The receiver narrows native candidate records and releases the decoded document after track preparation. Regional propagation and visibility use row blocks. The final phase-history pass releases each parsed TLE entry at its last read. Ranking and family confidence project one original track’s columns at a time, and ranking retains only feasible and nominated diagnostic rows. Conservative salvage and cavity nomination score the original catalogue in row tiles. Family confidence and signed context use the same three previous-orbit alignment samples. Signed fitting drops its label-only problem before refitting, releases each phase problem after its final read, and returns available glibc arena pages around the signed and optional joint-cavity stages. The unchanged five-refresh solver and original ranked hypotheses were used for both arms. DS26-0036 opened the joint-cavity gate, and DS29-0082 returned the signed incumbent.

The specialization runs once when staging the release. It draws the bounded algorithm bodies from the reviewed implementations, adds two runtime files, and changes eleven source files in the staged copy. The release uses the prior direct worker’s six scoped bindings for the compact projector and secant optimizer. The historical native bound still generates its validation and result boundaries at import. The separate native C build matches the original qualified binary digest exactly. The release’s copied sources and compiled numerical kernels supply the runtime on the measured Linux host. [Build recipe](../../../../tools/pipeline_eval/qualification/direct_lifetime_bundle.py) · [Staged source and donor ledger](bundle.json) · [Pre-inference lock](source-lock.json)

## Earlier timing controls and executed code

| Recording | Capped direct wall / CPU s | Uncapped direct wall / CPU s | Uncapped compact secant wall / CPU s | Earlier lifetime position interval wall / CPU s |
|---|---:|---:|---:|---:|
| DS26-0036 | 50.07 / 49.20 | 59.86 / 46.32 | 51.80 / 47.71 | 67.96 / 67.63 |
| DS29-0082 | 35.57 / 34.74 | 40.24 / 37.09 | 47.76 / 36.71 | 41.22 / 40.80 |

The earlier unrestricted runs used the same two pins and timed their ordinary launchers including projector build. The new wall starts at service launch with the projector prebuilt. The prior capped lifetime interval ran on CPU 18 after detector and handoff work inside its own service. The matched inputs and scientific outputs support parity across the scopes. The timing differences include those execution and load differences. [Sealed unrestricted direct pair](../../streamlined/direct-cavity/README.md) · [Sealed whole-IQ lifetime pair](../../streamlined/whole-pair/README.md)

Both capped workers reached 274 distinct staged or generated source paths. The observer counted 1,877 and 1,861 first-entry Python code locations, including import-time execution and the generated native-bound import. It recorded zero evaluation-runner, benchmark CLI, or qualification-module imports. The measured scientific closure still uses archived project localization modules and the platform’s NumPy, SciPy, SGP4 and glibc libraries. The released archive retains the complete older scientific distribution. It includes the same three prebuilt Linux x86-64 CPython 3.12 extensions as the original direct source package. Native-bound validation, the C projector, and the pinned host ABI still matter. The separate observer is outside the normal receiver module and appears only in the qualification launcher. The original executed source files are sealed separately from subsequent formatting changes to the builder and observer. [Exact executed qualification source](executed-sources.json) · [Source bundle](compact-cavity-source.tar.gz)

## Use the source bundle

Extract the bundle into a fresh local directory on a compatible Linux x86-64 CPython 3.12 host. The measured environment used NumPy 2.5.2, SciPy 1.18.1 with single-thread LP64 OpenBLAS, SGP4 2.27, and glibc. Use the direct CLI with the named stored GLRT, verified tracker configuration, causal TLE archive, and offered tile. The native manifest uses absolute paths, so build it in place after extraction. `--screen-center` supplies the original broader catalogue screen separately from `--tile`.

```sh
export PYTHONPATH="$PWD"
export TMPDIR="$local_disk_scratch"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1
python -B - <<'PY'
from pathlib import Path
from leo.analysis.localization_v4.backend import build_native
from tools.pipeline_eval.variants.orbit_projector import compile_kernel

build_native("native")
compile_kernel(Path("orbit_projector.so"))
PY
python -B -m tools.pipeline_eval.variants.v5_direct_lifetime \
  --native "$native_glrt" --native-sha256 "$native_sha256" --session "$session_id" \
  --track-config "$track_config" --config-sha256 "$config_sha256" \
  --archive "$causal_tle_root" --native-backend native/manifest.json \
  --library orbit_projector.so --tile "$tile_lat" "$tile_lon" \
  --screen-center "$screen_lat" "$screen_lon" --width-km 25
```
