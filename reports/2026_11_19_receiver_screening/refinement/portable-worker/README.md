# Run the standalone native receiver

The receiver takes a complete native GLRT capture, its Graph configuration, a causal TLE catalogue and one supplied region. It rebuilds the tracks and returns a JSON position decision for `c=0` and fitted `c`. The default solver is `joint`. Use `--solver smooth-clock` to fit the audited receiver oscillator model.

```sh
.venv/bin/python -m tools.pipeline_eval.variants.lean_receiver_cli solve \
  --native /data/native.json --track-config /data/track-policy.json \
  --catalogue /data/causal.tle \
  --catalogue-acquired-utc-ns 1792904651911878285 \
  --cutoff-utc-ns 1792908972366467298 --capture-utc-ns 1792908972455244319 \
  --region 37.906 -122.545 --region-id original --width-km 25
```

The timestamps above illustrate one archived capture. Supply the recorded UTC clock midpoint and the actual cutoff from your capture, plus the acquisition timestamp from the catalogue receipt. Use integer UTC nanoseconds. The worker verifies the cutoff and capture midpoint against the GLRT clock bracket, requires the catalogue to predate the cutoff and screens individual TLE epochs. Optional `--native-sha256`, `--catalogue-sha256` and `--track-config-sha256` bind the files to independent receipts. With those flags the launcher can skip its preliminary hash pass. The worker verifies every input hash before it publishes.

The input format is the complete canonical JSON detector export for a dual-receiver, 10 MS/s short scan with 20 ms probes and at most 360 seconds of support. The track configuration is the capture’s JSON document with a `config` object. This entry point begins with detector factors and searches the square region you supply. It is a passive local replay, with no antenna control, IQ detection or global search.

Read `result.arms.c0.latlon` and `result.arms.fitted_c.latlon` for published coordinates. Withholding leaves those fields null and provides a reason. `forced_latlon`, when present, is a diagnostic position. The JSON also contains conditional RF RMS, stage and process timings, peak resident and virtual memory, the canonical request hash, the solver and capture interface hash, and the complete source inventory. The command exits successfully for a completed fix or withholding decision. Operational failures and timeout return a nonzero exit status.

## Deploy without the benchmark checkout

Use a Linux Python 3.12 environment with Bubblewrap and install `numpy`, `scipy`, `sgp4` and `pydantic` with their required Python dependencies. The measured environment used NumPy 2.5.2, SciPy 1.18.1, SGP4 2.27 and Pydantic 2.13.4. The receipt records the actual installed versions.

```sh
.venv/bin/python -m tools.pipeline_eval.variants.lean_receiver_cli bundle \
  --solver smooth-clock --out /tmp/portable-native-receiver
python /tmp/portable-native-receiver/tools/pipeline_eval/variants/lean_receiver_cli.py \
  solve --help
```

The smooth-clock bundle supports both solvers. Use `bundle --solver joint` to omit the clock source. The launcher packages only the selected scientific files and mounts only the required installed dependency modules, the three input files and the Python runtime. The Linux sandbox masks the working tree and isolates the network, sets one numerical thread, and enforces 512 MiB of virtual address space before numerical imports. Predictions do not read v5, qualification reports, prepared tracks, a database or reference coordinates.

## Standard benchmark and verification

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS26-0036 \
  --variant portable_native_joint --pin --timeout 60 --require-inputs \
  --out /tmp/portable-native-smoke
```

The benchmark also exposes `portable_native_clock`. It obtains the three file paths from the frozen corpus adapter. A prepared-only row reports `unavailable`. The standard scorer writes the usual standalone position chart for each arm. [Standard smoke `c=0` chart](standard-c0.png) · [Standard smoke fitted `c` chart](standard-fitted-c.png)

The launch and packaging changes were checked by replaying stored factors. Each run reproduced its sealed scientific request hash, Graph digest, publication status and reason, and the entire two-arm position response exactly. Detached runs invoked the staged command from an empty directory with a nonexistent research `PYTHONPATH`. [Per-run timings, hashes and coordinates](parity.json) · [Capture-era joint study](../../factors/native-full/README.md) · [Capture-era smooth-clock study](../../factors/native-clock-full/README.md) · [Ordinary GLRT study](../../factors/iq-to-joint/README.md)

| Recording and factors | Solver | Decision | `c=0` / fitted `c` error (km) | Worker wall |
| --- | --- | --- | ---: | ---: |
| DS26-0036 capture-era | Joint | Published | 1.833 / 1.016 | 3.88 s |
| DS29-0082 capture-era | Smooth clock | Published | 0.465 / 0.499 | 2.92 s |
| DS26-0036 capture-era, alternate `r0` | Smooth clock | Withheld, weak position geometry | 23.319 / 23.376 forced | 4.66 s |
| DS26-0036 ordinary | Joint | Published | 1.112 / 0.454 | 4.10 s |
| DS29-0082 ordinary | Joint | Withheld, weak held-track support | 2.405 / 1.941 forced | 2.69 s |

The five final checks ran one worker at a time on x86-64 CPU23. Peak RSS was 140.9 MiB and peak virtual size was 376.6 MiB. The joint build used 19 first-party Python files and 4,274 physical lines. The smooth clock added one file and 255 lines. These five checks establish deployment parity on stored factors. The earlier studies carry the full-roof accuracy and timing comparisons. [Deployment hashes](deployment.json) · [Prepared-only benchmark receipt](prepared-only.json) · [Artifact seal](prediction-lock.json)

The standard screening gallery gives each measured input cohort its own chart, with the audited parent beside the portable launch. The ordinary DS29 withholding and the omitted-tile withholding appear in both calibration arms. The prepared-only receipt describes an input rejection before numerical inference. [Chart definitions](figures.json) · [Archive and request verification](figure-verification.json)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --variant portable_native_joint --variant portable_native_clock \
  --evidence reports/2026_11_19_receiver_screening/refinement/portable-worker \
  --out /tmp/portable-native-charts
```
