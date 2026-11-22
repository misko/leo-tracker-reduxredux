# Private checked-hash bytecode at ALGO08 startup

Both launchers run the same installed Python 3.12.14 with `-BPs`. In a private test with that executable, `-B` read a valid checked-hash cache. When the source changed, the next fresh process used the new source and left the old cache bytes untouched. A full-file SHA-256 check also detected a switched bytecode body whose header still matched the source. The installed release had 293 existing bytecode files under its first-party source trees. The frozen screened-stock bundle contained 1,651 Python sources and zero bytecode files under its copied `tools` tree. [Frozen configuration](measurements/screened-stock-freeze.json) · [Earlier lazy-import experiment](receiver-startup.md)

The release trial imports the installed CLI. The candidate trial runs the frozen screened-stock launcher's import and setup path, including the current lazy exports and the native-library pin checks, and stops immediately before `analyze`. It passes a private empty archive and an absent recording path to that boundary. Each timed pair uses fresh processes with the launchers' actual module search paths, identical stdlib and third-party cache lookup, and private Matplotlib and XDG cache directories. The source arm redirects the first-party cache lookups to absent private paths. The checked arm redirects the same paths to bytecode compiled from the original sources by the installed interpreter. Diagnostic runs outside the timed pairs check that both arms load the same first-party sources and that only the source arm compiles them. The controller verifies the 31 frozen bundle pins before and after, checks cache headers and full source and bytecode SHA-256 digests before and after, and removes the scratch files on exit. [Trial and integrity checks](bytecode_startup_trial.py)

The timings represent warm import-only reads and include interpreter startup, private cache lookup, import execution and process exit. They exclude private bytecode generation and any late imports first reached after `analyze`. The source and checked arms alternate order across eight pairs per comparison. The actual release reused valid cache for 289 of the 387 first-party paths it loaded. The candidate reused valid cache for all 180 installed-release paths it loaded and compiled all 118 paths from the frozen bundle.

| Comparison | Source median CPU | Checked median CPU | Paired CPU saving | Source median wall | Checked median wall | Paired wall saving |
|---|---:|---:|---:|---:|---:|---:|
| Release, all 387 sources | 2.212 s | 1.810 s | 0.393 s | 2.270 s | 1.868 s | 0.398 s |
| Screened-stock, all 298 sources | 1.234 s | 0.999 s | 0.219 s | 1.267 s | 1.033 s | 0.226 s |
| Screened-stock, 118 actual cache misses | 1.113 s | 1.015 s | 0.071 s | 1.130 s | 1.020 s | 0.081 s |

The broad candidate comparison replaces even the release caches that were already usable and measures the difference from forcing recompilation for those modules. Its largest paired wall saving was 0.285 s. The practical comparison kept those cache hits in both arms, saved 0.051–0.163 s wall time per pair, and recorded zero input blocks in the timed runs. Its median wall saving is approximately 6% of the northern pair's 1.277 s shortfall. These import-only measurements support leaving the freeze and launcher as they are. [All paired timings](measurements/receiver-bytecode-startup.json) · [Northern pair](measurements/screened-stock-north-inside.json)

```bash
p=/tmp/leo-algo08v2-2x-bench
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 80s "$r/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/bytecode_startup_trial.py \
  "$r" "$p/integration-screened-stock-finish" "$p/screened-stock-bytecode-startup.json"
```

Append `--candidate-misses-only` and use an alternate receipt path to keep existing release cache lookup in both arms and precompile only the candidate's observed source misses.
