# Combined successor on two original DS30 development recordings

DS30-0107 reproduced the charted withholding end to end. DS30-0016 passed signed metadata and port preflight but remained inadmissible after the single permitted resident-source preparation. The 0107 result therefore verifies the combined entry on an original early-withholding recording. No raw result here measures the combination on a new complete fix. [Short paired receipt](measurements/combined-small-panel-0107-pair.json) · [Positive conditioning receipt](measurements/combined-small-panel-0016-conditioning.json)

The trial reuses two private lookahead destinations, derives the frozen held-odd CFO correction from the newly authenticated detector, and applies the checked profiled posterior exporter at the installed grid port. The original 20/8 receiver, earlier-orbit dispatch, signed region, independent orbit catalogue checks and published rendering remain in their original path. The restore accepts only the qualified three-file prefetch delta between the exact charted `30cc3b04` and qualified slots build `bb4d1466`. [Protocol](combined-small-panel-protocol.md) · [Batch entry](combined_small_panel_entry.py)

## Measured negative case

Both live workers authenticated the complete signed DS30-0107 original, including its one 33,519,983-byte waveform member, typed index, manifest, offer and signed causal data. They reproduced the same native packet, with 27 admitted visits, two exclusions, and 54 ordered probes. Both returned `no_active_curvature`, null endpoints for `c = 0` and fitted `c`, and no owners, grid, path or PNGs. Installed ALGO08v3 preserved the same decision with its own 20 ms detector. The charted and trial receivers made no lookahead submissions. The trial did not enter the CFO Graph or the checked grid exporter. [Short paired receipt](measurements/combined-small-panel-0107-pair.json)

| DS30-0107 role | Raw launch to exit wall (s) | Independent verifier wall (s) | Verified wall (s) | Bootstrap CPU (s) | Acquisition wall (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Charted | 0.815482 | 0.001924 | 0.817406 | 0.530236 | 0.178429 |
| Trial | 0.765573 | 0.001875 | 0.767448 | 0.500284 | 0.156808 |
| Installed historical | 1.273173 | — | — | — | — |

The recorded startup-to-receiver wall was 0.396476 s charted and 0.338280 s trial. Each process occupied a separate official deferral, separated by the priority 0218 recording and replay work. No feature activated on this case, so the 49.958 ms verified difference supplies no evidence of a speed gain from the opt-ins. The two outer CPU and fault records cover only the namespace launcher. Bootstrap CPU excludes early interpreter and batch entry setup and final teardown. An off-slot no-waveform test confirmed that a meter in the same namespace observes the complete worker, with 0.275604 s worker CPU against 0.001397 s for the outer launcher. That meter was prepared for both positive workers. [Short trial and event timeline](measurements/combined-small-panel-0107-trial.json) · [Direct-parent meter](combined_small_panel_meter.py)

The next official 0218 attempt deferred again on storage **31.229 s** after the short trial exited. Its actual official successor launched **64.801 s** after the trial exit. The 0107 charted watcher missed the intermediate deferral and stopped without a child. The charted worker used a distinct later deferral, after both 0218 research replays had released. An earlier controller import error had stopped before process creation and produced no waveform access or measured child. [Aborted controller intent](measurements/combined-small-panel-0107-no-child.json)

## Positive case admission and contract check

DS30-0016's 808 issued visits and 991,734,597 compressed bytes are staged in 13 original members. Its passive preflight missed three members totaling 4,601,401 bytes of file extent beyond reported resident pages. The one CPU 3 idle-I/O pass addressed 1,094 missing pages, 4,481,024 nominal bytes. The helper took **0.237069 s wall / 0.021812 s CPU**, charged 1,095 major faults and 8,808 input blocks, and completed in **0.265203 s** with isolation and recheck. On this host the swap file resides on the root NVMe, separate from the waveform backing volume. The final independent full-scope check still missed 120,746 bytes of extent across two members. The admission declined without starting either 0016 worker. [Passive admission](measurements/combined-small-panel-passive.json) · [Paid conditioning](measurements/combined-small-panel-0016-conditioning.json)

The released Graph contract used the authentic archived 0016 packet. It consumed 29 CFO-only edits among 506 winners, assigned 301 observations across 12 tracks, and preserved the original native hash `5eea8c0d…`. This check opened zero waveform and causal files and reached zero position solves or grid calls. The historical installed same-request full fix took 10.861 s wall and binds both calibrated arms, RF, ordered owners, the full grid, path and eight PNGs. New fix accuracy and the combined map tolerance remain unmeasured. All 21 focused tests passed. [Released Graph readback](measurements/combined-small-panel-0016-graph-contract.json) · [Installed controls](stock-raw-repeat-protocol.md)

## Reproduction

The timed short pair used `ad15358a4` and ready pin `f8c812c9…`. The positive preparation used `fb4663173` and ready pin `832e697d…`. The controller always admits one worker per fresh official deferral, checks source residency, uses the nonblocking shared lock and releases it before independent verification. [Panel controller](combined_small_panel.py)

```sh
repo=/tmp/leo-v3-combined-small-panel
ready=/dev/shm/NEW-COMBINED-PANEL
python=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python
runner="$repo/reports/ALGO08/v3/combined_small_panel.py"
pin=$(sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" prepare "$ready")
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" condition "$ready" --ready-pin "$pin"
sudo -n -u leo taskset -c 3 nice -n 15 ionice -c3 env OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 "$python" -B "$runner" watch "$ready" --ready-pin "$pin" \
  --case "$case" --role "$role" --driver-pid "$official_pid"
```
