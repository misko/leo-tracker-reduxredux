# Native cost of restoring the scout refinement arithmetic

Rebuilding only the packed receiver’s scout delay-product object without compiler feedback increased native CPU by **2.49%** on the saved DS26 weak-carrier lanes. The restored build was still **2.70× faster** than the deployed receiver there. On the Austin excerpt the restored build cost **1.54–4.19%** more than packed across the measured and phase-null configurations. [All paired native timings and per-lane factor fields](measurements/receiver-cfo-native-trial.json.gz)

| Saved configuration | Lane calls per repeat | Deployed median CPU | Packed median CPU | Restored median CPU | Paired increase vs packed |
|---|---:|---:|---:|---:|---:|
| DS26 weak-carrier stereo | 36 | 388.96 ms | 140.74 ms | 143.95 ms | +2.49% |
| Austin measured, zero mixer center | 4 | 46.94 ms | 16.22 ms | 16.56 ms | +3.29% |
| Austin measured, shifted mixer center | 4 | 48.91 ms | 20.13 ms | 20.44 ms | +1.54% |
| Austin phase null, zero mixer center | 4 | 13.69 ms | 6.75 ms | 6.98 ms | +4.19% |
| Austin phase null, shifted mixer center | 4 | 14.57 ms | 7.50 ms | 7.75 ms | +3.39% |

The restored and packed builds returned identical bytes for all **74 factor exports**, including 30 rank-one factors, and the same continuation decisions and vote counts across 52 lane configurations. Both research builds agreed with deployment in factor presence, order, rank, integer and fractional epoch, and signed CFO. Relative to deployment, each research build changed the exact and rolled scores of 57 DS26 and 16 Austin factors. The largest absolute changes were **1.19×10⁻¹³** in the exact score and **5.08×10⁻¹⁴** in the rolled score. All eight Austin null configurations stayed empty. The sparse saved inputs produced no continued selections. These slices quantify native cost and preserve the archived controls. They did not encounter the three dense-recording CFO changes that motivated the restoration. [Earlier packed receiver](receiver-packed-cancellation.md) · [Independent archive and frame marks](austin-receiver.md)

The three native libraries and pilot assets match their SHA-256 pins. The restored digest is `6f2cc95d835ffcff8226a925dddca9d5b03d8fe6b06c159b165ac0807b805a91`. All six call orders appear twice for each input over 12 repeats. Each timed call runs the two-scan native entry point through signed cancellation and fractional verification whenever the scout admits those stages. Archive work, continuation, solving, and publication are outside the CPU timings. The Austin batches use the one measured antenna and both pilot edges, with −50 kHz on the lower edge and +50 kHz on the upper edge for shifted bounds. [Replay and integrity checks](receiver_cfo_native_trial.py)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist="$tree/reports/2026_11_19_receiver_screening"
flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 65s \
  "$tree/.venv/bin/python" "$t/receiver_cfo_native_trial.py" "$p" "$r/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$hist/physical/raw-source-audit.json" "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
~~~
