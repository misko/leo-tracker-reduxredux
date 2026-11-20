# Select a calibration from the compact paired receiver

The selected-calibration command returns one requested fit after the compact receiver makes its original paired decision. Conservative refits reject the union of failing tracks from both calibrations. The history and signed policies require the pair to pass, and a cavity proposal must qualify under both calibrations even when the corrected zero-calibration score ranks it. The optional 20 m interior policy can withhold both positions when either endpoint touches a tile face. The command requires an explicit publication policy. [Study protocol](PROTOCOL.md)

The reduced worker omits the two terminal conservative association reports. The standalone pipeline uses the retained mask, fit records and phase references in later stages. It never reads these reports. The worker also shares the exact direct phase-width and causal receipt views between family weighting and signed fitting when the scan and ordered catalogue labels match. Callers receive separate copies. The original paired entry and release remain available.

```sh
.venv/bin/python -m tools.pipeline_eval.variants.arm_execution install \
  --base /path/to/verified/phase-release --out /var/tmp/selected-phase-release

.venv/bin/python -m tools.pipeline_eval.variants.arm_execution select \
  --receiver /var/tmp/selected-phase-release \
  --request /path/to/compact-request.json --request-sha256 SHA256 \
  --calibration fitted_c --publication paired-interior --timeout 180
```

The request contains `compact` and `causal_snapshots` objects. The compact object supplies `native`, `native_sha256`, `archive`, `track_config`, `config_sha256`, `session`, `tile`, `screen_center` and `width_km`. The causal object maps each TLE filename to its bare SHA-256. The example request's SHA-256 is `8f78d35a8291ce296fbdc10e49f2f1df3cce1be5a15e8f0d133e3a1973b82ff2`. The command validates the installed source and native manifest, then emits a `compact-selected-calibration-v1` object with the requested fit, paired decision digest and applicable frequency and guard evidence. The qualified runtime used one CPU and an external 512 MiB cgroup with zero swap per service. `--timeout` caps the command's numerical child. [Example truth-free request](example-request.json)

## Measured results

All 12 numerical services completed under the 180-second cap. Each of the eight selected-calibration runs reproduced the installed paired worker's requested endpoint, conditional Doppler RMS, frequency score and publication. The shared paired decision digest matched for both selected runs on each recording. The original guard withheld both DS26-0070 positions and retained identical forced diagnostics. [Prediction seal](prediction-lock.json) · [Exact comparisons](parity.json) · [Guard chart](charts/c0/arm-execution-edge.png)

| Input | Original pair CPU | Selected zero-c CPU | Selected fitted-c CPU | Peak range |
| --- | ---: | ---: | ---: | ---: |
| DS26-0070, established shifted offer | 78.82 s | 68.42 s | 82.40 s | 310.3–326.4 MiB |
| DS26-0241, hash-selected original offer | 95.40 s | 93.43 s | 94.92 s | 371.4–389.7 MiB |
| DS29-0082, established original offer | 37.64 s | 40.79 s | 37.10 s | 304.7–317.7 MiB |
| DS29-0174, hash-selected original offer | 73.13 s | 67.53 s | 73.63 s | 335.1–342.3 MiB |

Five of eight selected runs used less CPU. The median difference was 0.51 CPU-seconds saved (0.98%), with individual differences from 3.58 seconds slower to 10.41 seconds faster. Elapsed wall was 37.28–134.65 seconds across the 12 services. The selected worker reused two or three causal phase views per run and omitted 16 unused association reports across its eight runs. Both numerical arms still ran on each request. Each selected service nominated 13–28 orbit families. The four recordings produced zero eligible cavity offers. The paired cavity requirements are established by the pinned producer code. [Timing chart](stage.pdf) · [Per-run timing and memory](stage.csv) · [Resource and policy traces](resources.json)

| Recording | Position error, zero / fitted | Conditional Doppler RMS, zero / fitted |
| --- | ---: | ---: |
| DS26-0241 | 0.600 / 0.685 km | 79.253 / 79.315 Hz |
| DS29-0082 | 0.568 / 0.516 km | 97.003 / 96.684 Hz |
| DS29-0174 | 0.886 / 0.918 km | 95.404 / 95.518 Hz |
| DS26-0070, withheld | 2.165 / 2.148 km forced | 83.128 / 83.038 Hz |

The three original offers published in both calibrations. The standard roof charts show their four original v5 reference options using the original offers. The shifted DS26-0070 comparison has a separate chart. [Zero-c roof](charts/c0/arm-execution-roof.png) · [Fitted-c roof](charts/fitted_c/arm-execution-roof.png) · [Per-arm geographic and frequency scores](scores.csv)

The first nine ordinary service launches stopped during setup because their archived tile dictionaries omitted the 25 km default. The corrected lock supplies that width explicitly and preserves every other input and execution setting. The measured launcher snapshot preserves the exact earlier source. The reusable launcher now fills the default when the archive omits it. [Initial setup receipts](setup-attempts.json) · [Normalized ordinary inputs](ordinary-execution-lock.json) · [Measured launcher](launcher-at-measurement.py.gz)
