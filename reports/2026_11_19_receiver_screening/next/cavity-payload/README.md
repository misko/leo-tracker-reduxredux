# A standalone position receiver in 78 project source files

The smaller package returned the same eight calibrated positions as the complete direct lifetime package in four same-core pairs. Conditional Doppler RMS, frequency objectives, publication decisions, initial branch counts, orbit projection counts and every other recorded scientific counter also matched. Each service ran under a real 512 MiB cgroup with zero swap. [Ordinary GLRT position chart](../charts/fitted_c/cavity-payload-ordinary.png) · [Capture-era holdout chart](../charts/fitted_c/cavity-payload-capture-era.png) · [Both calibrations and individual scores](scores.csv)

| Recording | Detector inputs | Full → small wall | Full → small CPU | Full → small peak | Zero / fitted horizontal error |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0036 | Ordinary | 48.09 → 41.70 s | 46.38 → 41.31 s | 403.4 → 267.9 MiB | 0.218 / 0.180 km |
| DS29-0082 | Ordinary | 33.94 → 27.01 s | 32.34 → 26.57 s | 410.7 → 275.0 MiB | 2.789 / 2.654 km |
| DS26-0112 | Capture-era holdout | 66.81 → 63.10 s | 65.58 → 61.88 s | 492.2 → 338.2 MiB | 1.027 / 1.049 km |
| DS29-0127 | Capture-era holdout | 40.39 → 34.17 s | 38.68 → 33.86 s | 402.6 → 264.1 MiB | 0.633 / 0.579 km |

These times begin at stored GLRT output and include program startup. Run order was counterbalanced, with one execution of each package per recording on the same x86 core. The two holdouts were selected by recording ID before scoring. They share the original receiver installation. Wall time fell 5.6–20.4%, and peak cgroup charge fell by 135.5–154.0 MiB. The receiver also ran at the end of an actual complete saved-IQ replay on DS29-0082. [Predeclared protocol](PROTOCOL.md) · [Measured stage boundaries and resources](resources.csv) · [Whole-IQ result](../direct-whole/README.md)

## What was removed

The complete deployment carried **1,042 project files** and 334,440 Python source lines. The smaller distribution carries **78 project files** and 11,885 Python source lines. Its compressed source is 140,131 bytes, compared with 2,986,146 bytes for the complete sources repacked the same way. At run time the isolated interpreter loaded 76 project source paths, down from 274. Both numerical C libraries rebuilt byte-identically on this host. The installer adds a launcher and a private package initializer, then builds the two libraries. These counts exclude the Python interpreter and third-party dependencies. [Per-source and binary digests](package.json) · [Both distributions and input bindings](source-lock.json)

Four mixed-purpose modules now contribute only their required preparation, projection and assignment functions. The packager copies those definitions from the released source and follows their imports, including imports inside functions. Four platform package initializers previously exposed unrelated registry, storage and plotting code. The private executable imports concrete numerical modules under those packages. Each successful run checked the file origins of every loaded project module. The v5 assignment, recovery and position mathematics remain the parts one must understand to change the estimator. [Distribution builder](../../../../tools/pipeline_eval/qualification/cavity_payload.py) · [Import and resource measurements](observations.json.gz) · [Eight-arm equivalence](parity.json)

## Build and use

Build into a new local directory at its final location. The verified environment used Linux x86-64 with glibc, CPython 3.12, a C compiler, NumPy, SciPy, Pydantic and SGP4 from the project environment. The native build manifest records the library locations. This command needs the released source and its digest ledger only. It runs without the radio corpus, historical checkouts or a database. [Download the source](receiver-source.tar.gz) · [Release checksums](prediction-lock.json)

```sh
.venv/bin/python -m tools.pipeline_eval.cavity_runtime /tmp/leo-cavity
.venv/bin/python -IB /tmp/leo-cavity --help
```

The receiver accepts an authenticated native GLRT document and track configuration, the recording session identifier, a causal TLE archive, and an offered region. Use an immutable copy of the recording's Space-Track snapshot inventory, including the 48/72-hour history needed to form the orbit priors. A later backfill can change the selected history. The archive reader verifies the digest of each snapshot it reads. Supply both centers in latitude/longitude degrees. The screen center controls the initial visible-satellite search. The default profile checks that its local tile stays clear of the poles and the longitude discontinuity, and that both centers use a continuous longitude range. A published fix contains both position estimates and their conditional Doppler RMS in one JSON document.

```sh
.venv/bin/python -IB /tmp/leo-cavity \
  --native "$NATIVE" --native-sha256 "$NATIVE_SHA256" --session "$SESSION_ID" \
  --track-config "$TRACK_CONFIG" --config-sha256 "$CONFIG_SHA256" \
  --archive "$TLE_ARCHIVE" --tile "$TILE_LAT" "$TILE_LON" \
  --screen-center "$SCREEN_LAT" "$SCREEN_LON" --width-km 25
```

The numerical executable sets its math libraries to one thread. To enforce the measured memory limit on a Linux host with a user systemd manager, prefix the absolute Python command with `systemd-run --user --wait --pipe -p MemoryMax=512M -p MemorySwapMax=0`. A target-board measurement is still needed for an embedded runtime claim.

Two additional profiles can be built into separate directories with the same installer. Add `--profile majority` to require a majority of compatible tracked points before the expensive recovery fit. Two simulated far omissions withheld and a near omission still published. Add `--profile longitude` to use wrapped longitude for local tiles up to 25 km wide and centers within 150 chart km, at latitudes up to 80° in magnitude. This version published on a synthetic date-line crossing and on a deliberately wrong geographic offer. Each profile is individually bound to its measured source. [Majority evidence](../standalone-majority/README.md) · [Longitude evidence](../longitude/README.md)

The installed commands were exercised outside the repository on the measured DS29-0082 ordinary input (`compact`), a diagnosed synthetic far omission (`majority`), and the synthetic date-line crossing (`longitude`). External cgroup samples verified the configured 512 MiB limit and zero swap. Each run reproduced its archived publication decision, both calibrated outcomes and scientific counters. The harness also retains startup failures and supervisor timeouts. [Installed-entry receipts](installed-check.json) · [Measured builder](measured-cavity_payload.py.gz) · [Measured run driver](measured-cavity_payload_trial.py.gz)
