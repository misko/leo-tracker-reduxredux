# Compact v5 with explicit numerical bindings

The standalone position receiver now passes its projector directly to each scan and calls the existing compact secant optimizer from the position model. The previous entry temporarily replaced six module bindings for every solve and held a lock while the fit ran. The opt-in package also removes the displaced Gauss–Newton implementation, an unused multiprocess backend and two private command wrappers. It keeps the directory launcher, the prepared-native schema, the original NumPy geometry used by early conservative recovery, and the existing bounded projection and memory-release paths. [Installed source diff](installed-change.patch)

The measured standalone distribution goes from **11,994 to 11,812 Python lines** and **516,316 to 509,676 source bytes**. It removes eight Python function definitions and one class. Both installations carry 78 released source files and two launcher/package files. Both C sources and their compiled binaries match byte for byte. The native grouped-likelihood wrapper still derives its original Python validation and reporting functions at import, with its original fallback and binary and provider checks. The standalone numerical process loads its project modules from the installed directory. The project checkout is used at install time to verify and transform the released sources. [Source and input lock](source-lock.json) · [Qualified source distribution](receiver-source.tar.gz) · [Package hashes](package.json)

## Replay comparison

All six services returned fixes. The new receiver exactly matches phase-release in both calibrated coordinates, conditional Doppler RMS, frequency objectives, publication and scientific counters on all three recordings. Initial ranks and winner, conservative support and the ordered cavity nominations also match. Both receivers ran one cavity recovery trial on DS26-0036 and one on DS29-0357, and each trial retained the incumbent. The salted holdout DS26-0090 produced no cavity offer. [Decision parity](parity.json) · [Zero-c position chart](charts/c0/acquisition-frontier-compact-cut.png) · [Fitted-c position chart](charts/fitted_c/acquisition-frontier-compact-cut.png)

All pairs use the original capture-era GLRT factors, track settings, causal catalogue and geographic offer. DS26-0090 was the first salted draw from 12 eligible sealed rows. Each run used a fresh Linux cgroup at 512 MiB and zero swap with one numerical thread. Each pair used the same core, with candidate-first order on the holdout. The same lightweight observer recorded decisions, process resources and dependency imports for both executables. [Protocol](PROTOCOL.md) · [Terminal service receipts](receipt.json)

| Recording | Service wall, stock → cut | Process CPU, stock → cut | Cgroup peak, stock → cut | Process peak RSS, stock → cut |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 70.54 → 69.87 s | 67.39 → 68.91 s | 265.8 → 262.4 MiB | 304.5 → 301.9 MiB |
| DS29-0357 | 117.49 → 125.25 s | 115.62 → 120.55 s | 311.2 → 309.8 MiB | 349.8 → 349.0 MiB |
| DS26-0090 | 91.56 → 96.46 s | 88.44 → 89.45 s | 327.6 → 309.8 MiB | 344.7 → 348.1 MiB |

Service wall covers launch and complete position inference from the stored factors. Process CPU covers the observed launcher and numerical execution. Each candidate cgroup peak was lower, with a maximum difference of 17.8 MiB. The three pairs show no runtime improvement. Runtime snapshots show the same 14 external import roots and remove the `multiprocessing` standard-library root. Both runs execute the directory launcher and retain the same 77 numerical source paths in the import snapshot. Multiprocessing also held an extra launcher module alias in the stock snapshot. [Resources and stage timings](resources.csv) · [Import inventories](imports.json)

| Recording | Horizontal error, zero / fitted c | Conditional Doppler RMS, zero / fitted c |
| --- | ---: | ---: |
| DS26-0036 | 1.260 / 1.196 km | 74.760 / 74.682 Hz |
| DS29-0357 | 0.436 / 0.434 km | 64.816 / 64.876 Hz |
| DS26-0090 | 0.935 / 0.929 km | 79.018 / 78.722 Hz |

The table applies to both packages. The fitted calibration has a different geographic and frequency effect on each recording. On DS29-0357, the fitted arm is about 2 m closer to the reference while conditional RMS rises approximately 0.06 Hz. [Both-arm scores and frequency objectives](scores.csv)

## Install the opt-in receiver

Use a new local directory and the same CPython 3.12, NumPy, SciPy, Pydantic, SGP4, C compiler and single-threaded SciPy LP64 provider required by phase-release. The measured host used glibc on Linux x86-64. The existing installed profiles remain available from their original installer.

```sh
.venv/bin/python -m tools.pipeline_eval.compact_cut /path/to/compact-cut
.venv/bin/python -IB /path/to/compact-cut --help
```

Use the same `--native`, `--native-sha256`, `--session`, `--track-config`, `--config-sha256`, `--archive`, `--tile`, `--screen-center` and optional `--width-km` flags as phase-release. The installer writes its native manifest for the final directory. Each result contains the two calibration arms, conditional Doppler RMS, frequency objectives for completed fits and the status. [Base launcher flags and memory-limit example](../../next/cavity-payload/README.md)
