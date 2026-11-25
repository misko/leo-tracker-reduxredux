# Combined successor on resident DS30 development recordings

The exact charted field raw entry and the combined trial passed metadata-only preflight on DS30-0016 and DS30-0107. The trial reuses the two private lookahead destinations, derives the frozen held-odd CFO correction from the newly authenticated detector, and applies the checked profiled posterior exporter at the installed grid port. The original 20/8 receiver, earlier-orbit dispatch, signed region, independent orbit catalogue checks and published rendering remain in the original path. The restore accepts only the qualified three-file prefetch delta between `30cc3b04` and `bb4d1466`. [Protocol](combined-small-panel-protocol.md) · [Batch entry](combined_small_panel_entry.py)

The unconditional passive preflight missed 0016 residency on three of its 13 members, with 4,601,401 bytes of missing file extent relative to whole resident pages. The complete original provides 808 issued visits and 991,734,597 bytes of compressed payload. Its second stored format and derived detector packets are not enrolled waveform operands. DS30-0107 had all 55 files resident, including its one 33,519,983-byte member, typed indexes, manifests, offer and signed causal bodies. Both cases passed untouched canonical session and raw authority from their privately mounted tmpfs originals. [Passive admission record](measurements/combined-small-panel-passive.json)

On the authenticated archived 0016 detector, a no-solve contract replay confirmed 29 signed CFO changes among 506 winning observations. The ordinary released Graph consumed those rows, assigned 301 observations across 12 tracks, and returned `tracks_prepared`. The input detector hash remained `5eea8c0d…`. The contract replay did not open waveform or causal bodies or call the solver or grid. The 20 tests cover scope and sealed order, the actual publication hook, the withheld route, the read-only page helper, Graph and checked grid behavior. [Released Graph readback](measurements/combined-small-panel-0016-graph-contract.json)

The previous same-request installed ALGO08v3 repeats authenticate a complete 0016 fix in 10.861 s wall and a 0107 withhold in 1.273 s wall. The positive reference binds both calibration arms, ordered owners, complete grid, path and eight PNGs. These clocks come from earlier independently verified raw runs. [Installed controls](stock-raw-repeat-protocol.md)

The combined 0107 trial processed the complete original and withheld with `no_active_curvature` in **0.765573 s wall**, plus **0.001875 s** for independent verification. It reproduced 27 admitted visits, two exclusions, 54 probes and the original raw authority. Both calibrations returned null endpoints. The one-member source supplied zero lookahead buffers and the early withholding route opened neither optional positive port. The numeric worker spent **0.500284 CPU s** within the authenticated bootstrap, excluding earlier process startup and final teardown. Parent fault and CPU counters covered only the bwrap launcher and cannot stand for the numerical child. The later metadata-only contract check verified direct-parent accounting within the same capsule. [Verified trial and official event timeline](measurements/combined-small-panel-0107-trial.json) · [Meter](combined_small_panel_meter.py)

The nearest subsequent official attempt deferred again on storage, **31.229 s** after the 0107 trial exited. The actual 0218 successor launched **64.801 s** after that trial exit. The 0107 charted watcher began after the intermediate deferral and found no fresh event before the official successor started. Its matched child remains outstanding. The earlier controller import error occurred before process creation and produced no waveform access or measured child. [Aborted controller launch intent](measurements/combined-small-panel-0107-no-child.json)

The pinned measured root is `/dev/shm/leo-v3-combined-small-panel-ready07`, with `ready.json` SHA-256 `f8c812c9daed138f83a5537564a1f9a036e4543f65dd188892eddb0d6dd6dc4e`. The qualified owner observes new official deferrals, opens the shared lock nonblocking and releases it before standard publication verification. The special `--pending-0218` window expired at the official successor launch. The remaining raw analysis and charged conditioning follow the prospective 0218 replay priority. [Panel controller](combined_small_panel.py)

```sh
repo=/tmp/leo-v3-combined-small-panel
ready=/dev/shm/leo-v3-combined-small-panel-ready07
pin=f8c812c9daed138f83a5537564a1f9a036e4543f65dd188892eddb0d6dd6dc4e
python=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python
runner="$repo/reports/ALGO08/v3/combined_small_panel.py"
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" condition "$ready" --ready-pin "$pin"
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" watch "$ready" --ready-pin "$pin" \
  --case "$case" --role "$role" --driver-pid "$official_pid"
```
