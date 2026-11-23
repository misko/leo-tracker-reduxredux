# Blind empty-lane screening before full v3 acquisition

The blind screen did not preserve the physical data. The calibrated threshold lost **four factors and three continuation selections** on the contiguous dense replay, and lost factors on both the later dense and weak-carrier slices. The dense replay cost **0.782–0.783 s CPU** with screening versus **0.756–0.763 s** for stock. Even a hindsight threshold with 100% observed dense factor-lane recall could skip only **9 of 110 empty lanes**. [Frozen protocol](occupancy-protocol.md) · [Per-lane measurement and timing receipt](measurements/occupancy.json.gz)

## Frozen screen and reference

Every feature reads sparse samples from one original CI16 antenna. Inverse flatness and 95th-percentile-to-median peakiness use the averaged power from four 256-sample Hann FFTs over the full band. Repetition uses the maximum over eight fixed 96-sample tiles of their median normalized complex covariance over three adjacent frame pairs. Taking the magnitude removes arbitrary phase between frames. These features use the nominal frame rate and zero information about LO, site, published score, continuation or CFO. [Feature code](occupancy_trial.py)

Seed 5882 assigned DS30-0008’s visits 0–63 to calibration, 64–127 to the adjacent held member and every fourth visit of 512–575 to the later check. Each assignment kept both antenna lanes together. Calibration chose inverse flatness with threshold 0.1498462420, retaining every training lane that emitted any stock factor. Even in training it skipped only 4 of 54 empty lanes. The real weak archive and the saved southern simulation stayed outside calibration. Four authenticated signed members and the 18 archived weak stereo windows supplied all waveform data. The adjacent held block shares a physical recording with calibration, the later block samples only one member, and neither makes these a new-site qualification. The later sample uses sparse visits and has no continuous donor history replay.

| Slice | Stock nonempty / empty lanes | Empty lanes skipped | Missed nonempty lanes / factors | Unselected nonempty lanes skipped |
|---|---:|---:|---:|---:|
| Dense adjacent held member | 72 / 56 | 6 | 3 / 4 | 0 |
| Dense later member, every fourth visit | 23 / 9 | 1 | 2 / 3 | Unmeasured |
| DS26 weak archive | 36 / 0 | 0 | 2 / 3 | 2 |
| South containing simulation | 16 / 80 | 32 | 0 / 0 | 0 |
| Dense complete prefix, including calibration | 146 / 110 | 10 | 3 / 4 | 0 |

An empty lane means that installed v3 emitted no raw factor. It provides a stock-negative comparison and does not establish physical silence. Unselected nonempty lanes can supply later history. The masked replay sees only factors from paid calls and advances released continuation with an empty slot on a skip. It compared all 256 dense opportunities and lost three of the original 84 selections. The sparse weak sample had no selected continuation result and exposes loss of two potential donors. The simulated southern replay preserved its original continuation. [Released continuation](../../../tools/pipeline_eval/variants/carrier_continuation.py)

## High-recall operating points and cost

These operating points choose a threshold with hindsight within each described slice and hold all input work fixed. A hypothetical free screen receives the gross saving before paying for features. The calibrated Python trial computed all three score components on every lane, averaging 0.191 ms per dense prefix lane. Timing covers resident I/Q through native detection and continuation. It excludes reading the archive, sealing detections and solving.

| Dense full prefix score | Empty skips at 100% / 99% / 95% observed nonempty recall | Net CPU saved at 100% / 99% / 95% recall |
|---|---:|---:|
| Inverse flatness | 9 / 10 / 10 | −36.9 / −31.2 / −8.0 ms |
| Spectral peakiness | 2 / 3 / 10 | −46.3 / −41.2 / −6.5 ms |
| Frame repetition | 0 / 0 / 5 | −48.9 / −45.3 / −14.6 ms |

At full observed recall even a free evaluation of the best dense score would skip only about 12 ms of detector work in this prefix. The later dense member offered zero empty skips at full recall for all three scores. By contrast, all three scores separated the 16 positive and 80 empty lanes of the simulated southern sample with hindsight. The frozen dense threshold skipped 32 southern empties and saved **12.6–12.7%** CPU in its two actual resident replays. The difference indicates that the simulated positive and empty lanes are easier to separate in this slice. It supplies no evidence of matching selectivity on real weak or dense measurements. A dedicated cheaper kernel would reduce screen cost while leaving the observed physical recall problem intact.

The pinned historical dense ledger gives a stronger ideal bound. Free, perfect occupancy could skip all 110 stock-empty lanes and preserve every factor and history slot, removing **132.039 of 678.314 ms native CPU**, or **19.5%**. Relative to the old matched verified acquisition clocks that is about **13.3% of complete acquisition CPU**. The previous 16.3% complete saving oracle also chooses some nonempty slots to drop with hindsight, a different permission. Prior delayed continuation used measured causal support and stored original waveforms. Neither study established a waveform-only occupancy classifier. This trial stops the tested scores without a full raw run. [Perfect schedule](continuation-skip.md) · [Delayed continuation](../single-core-2x/deferred-continuation.md)

## Reproduce

Three component tests passed, covering power-scale invariance, phase-free repetition, threshold ties, donor accounting and grouped assignments. The bounded raw replay uses one low-priority CPU under the shared lock.

```sh
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 50s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.occupancy_trial /opt/leo-algo08/algo08v3/payload/receiver.so "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk \
  /tmp/leo-regional-qZJKBw4W/public > /var/tmp/leo-occupancy.json
lock env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_occupancy_trial.py
```
