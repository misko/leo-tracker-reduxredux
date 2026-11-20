# Installed 20 m interior profile

The opt-in `interior` profile runs the qualified 20 m publication rule in the standalone phase-release receiver. The regular `python -IB /path/to/receiver` invocation fits the two calibration arms once and applies the rule to the fitted tile immediately before writing JSON. The rule withholds both arms when either fit is within 20 m of a tile face. It keeps the numerical coordinates as forced diagnostics and preserves conditional RF RMS and frequency objectives.

## Recorded offer parity

| Recording and offer | Installed publication | Geographic error, zero / fitted | Conditional RF RMS, zero / fitted | Direct wall | Cgroup CPU | Charged peak |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0102, near inside | Both arms | 0.872 / 0.850 km | 64.882 / 64.932 Hz | 91.69 s | 90.96 s | 298.07 MiB |
| DS26-0070, near omission | Both withheld | 2.958 / 2.937 km, forced | 82.185 / 82.126 Hz | 76.30 s | 75.38 s | 267.54 MiB |

Both services completed under 512 MiB with zero swap, from an out-of-checkout directory. The cgroup samples observed one standalone Python process on CPU 12 and CPU 13 respectively. Coordinates, forced coordinates, conditional RF RMS, frequency objectives, fitted tile margins and status exactly match the corresponding sealed decisions from the separate stdin filter. CPU values come from service cgroup samples. Direct wall includes interpreter startup, input preparation, the two-arm solve, publication and JSON output. The earlier filter timing has a separate boundary.

These two offers were chosen from known outcomes to verify the installed entry. The broader six-offer study includes a containing offer that the policy withheld. A wrong tile can still contain an interior numerical fit. [Earlier measured offers](../measured-boundary-policy/README.md) · [Exact numerical parity](parity.json) · [Resource receipts](resources.json) · [Both-arm scores](scores.csv) · [Zero-c figure](charts/c0/installed-interior.png) · [Fitted-c figure](charts/fitted_c/installed-interior.png)

## Build and run

```sh
python -m tools.pipeline_eval.cavity_runtime "$RECEIVER" --profile interior
python -IB "$RECEIVER" \
  --native "$NATIVE" --native-sha256 "$NATIVE_SHA256" --session "$SESSION" \
  --track-config "$TRACK_CONFIG" --config-sha256 "$CONFIG_SHA256" \
  --archive "$TLE_ARCHIVE" --tile "$TILE_LAT" "$TILE_LON" \
  --screen-center "$SCREEN_LAT" "$SCREEN_LON" --width-km "$WIDTH_KM"
```

The original default remains `compact`. The four existing profiles rebuilt byte-for-byte at the same absolute paths, including all 337 installed files across their trees and their compiled libraries. The interior build adds the guard module and its call in a dedicated generated launcher. Its scientific source files and compiled native objects match the measured phase-release package. The only guard-module source change imports the already installed optimizer's identical 0.020 km constant. The guard functions retain the original AST. Compilation used an ext4 `TMPDIR` after the host temporary filesystem rejected the initial compiler invocation. The compressed builder and direct replay harness bind the exact bytes used for measurement. [Legacy file comparison](compatibility.json) · [Installed launcher](installed-entry.py.txt) · [Installed policy](installed-rule.py.txt) · [Source and input seal](source-lock.json) · [As-run source checksums](as-run-sources.json)
