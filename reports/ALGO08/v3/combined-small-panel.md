# Combined successor on resident DS30 development recordings

The exact charted field raw entry and the combined trial passed metadata-only preflight on DS30-0016 and DS30-0107. The trial reuses the two private lookahead destinations, derives the frozen held-odd CFO correction from the newly authenticated detector, and applies the checked profiled posterior exporter at the installed grid port. The original 20/8 receiver, earlier-orbit dispatch, signed region, independent orbit catalogue checks and published rendering remain in the original path. The restore accepts only the qualified three-file prefetch delta between `30cc3b04` and `bb4d1466`. [Protocol](combined-small-panel-protocol.md) · [Batch entry](combined_small_panel_entry.py)

The unconditional passive preflight missed 0016 residency on three of its 13 members, with 4,601,401 bytes of missing file extent relative to whole resident pages. The complete original provides 808 issued visits and 991,734,597 bytes of compressed payload. Its second stored format and derived detector packets are not enrolled waveform operands. DS30-0107 had all 55 files resident, including its one 33,519,983-byte member, typed indexes, manifests, offer and signed causal bodies. Both cases passed untouched canonical session and raw authority from their privately mounted tmpfs originals. [Passive admission record](measurements/combined-small-panel-passive.json)

On the authenticated archived 0016 detector, a no-solve contract replay confirmed 29 signed CFO changes among 506 winning observations. The ordinary released Graph consumed those rows, assigned 301 observations across 12 tracks, and returned `tracks_prepared`. The input detector hash remained `5eea8c0d…`. The contract replay did not open waveform or causal bodies or call the solver or grid. The 19 tests cover scope and sealed order, the actual publication hook, the withheld route, the read-only page helper, Graph and checked grid behavior. [Released Graph readback](measurements/combined-small-panel-0016-graph-contract.json)

The previous same-request installed ALGO08v3 repeats authenticate a complete 0016 fix in 10.861 s wall and a 0107 withhold in 1.273 s wall. The positive reference binds both calibration arms, ordered owners, complete grid, path and eight PNGs. These clocks come from earlier independently verified raw runs. Current preflight records no new raw timing. [Installed controls](stock-raw-repeat-protocol.md)

The pinned prepared root is `/dev/shm/leo-v3-combined-small-panel-ready05`, with `ready.json` SHA-256 `3adc9db1e463eaa2913e8c786db9373486a6d47c3b8e56854a55f494d8154a7c`. Run one watcher per registered arm after the higher-priority work clears. The qualified owner only observes new official deferrals, opens the shared lock nonblocking and releases it before standard publication verification. The only writes from its separately charged 0016 conditioning process are its private receipt and process records. [Panel controller](combined_small_panel.py)

```sh
repo=/tmp/leo-v3-combined-small-panel
ready=/dev/shm/leo-v3-combined-small-panel-ready05
pin=3adc9db1e463eaa2913e8c786db9373486a6d47c3b8e56854a55f494d8154a7c
python=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python
runner="$repo/reports/ALGO08/v3/combined_small_panel.py"
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" condition "$ready" --ready-pin "$pin"
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" watch "$ready" --ready-pin "$pin" \
  --case "$case" --role "$role" --driver-pid "$official_pid"
```
