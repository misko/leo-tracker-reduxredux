# Exact phase-forecast preparation on weak DS30-0016

Reusing the scalar Julian split at each validation UTC and simplifying scalar clipping lowered median paired forecast CPU time by **44.49 ms** across four order-balanced pairs on the genuine weak history. Every full forecast digest matched. The single complete saved comparison reproduced the original science and all eight figures. The weak solver still needs substantially larger savings. [Frozen protocol](exact-phase-forecast-protocol.md) · [Receipt](measurements/exact-phase-forecast.json)

The earlier causal table already caches canonical element exports and previous catalogue parsing. Its live audit found that all 20,634 scalar combinations of orbital element and date were distinct. The forecast still converted UTC to a Julian day and fractional day separately for each transition. The genuine history has 9,776 versions for 1,449 satellites in 20 snapshots. The 6,878 accepted transitions shared 13 UTCs, so the bounded per-call cache avoided 6,865 repeated conversions. Every SGP4 record is still freshly constructed and propagated. The replacement uses the released binary64 split, retains dot product and reduction order, and handles saturation on the same finite scalar inputs. The measured effect includes both the date cache and the scalar arithmetic change. [Prior work audit](live-orbit-setup-audit.md) · [Prototype](exact_phase_forecast.py)

| Paid forecast sample | Order | Stock CPU (ms) | Variant CPU (ms) | Saved CPU (ms) |
|---|---|---:|---:|---:|
| 1 | Stock first | 255.490 | 212.602 | 42.888 |
| 2 | Variant first | 256.912 | 212.886 | 44.026 |
| 3 | Stock first | 259.258 | 211.465 | 47.793 |
| 4 | Variant first | 257.919 | 212.965 | 44.955 |

The four-pair median passed the frozen 40 ms floor. Both subsequent fresh processes took one normal saved detector handoff under the same installed publication, checked native libraries, causal archive, supplied offer, Graph reuse and complete-grid implementation. Timing includes the per-forecast source pin check. Output and font state were on tmpfs. The workers ran on Gauss CPU 2 under the shared lock, at nice 15 and best-effort I/O priority 7, with one numerical thread. There were zero waveform reads and zero process input blocks in either complete run. The single pair ran stock first, and only the four alternating forecast measurements support a repeated effect. [Saved handoff and comparison](exact_phase_forecast_trial.py) · [Existing matched saved control](cumulative-grid-projection.md)

| Complete saved pair, stock first | Stock CPU (s) | Variant CPU (s) | Stock elapsed (s) | Variant elapsed (s) |
|---|---:|---:|---:|---:|
| Forecast | 0.261360 | 0.210104 | 0.261366 | 0.210150 |
| Numerical path | 2.526528 | 2.438195 | 2.526608 | 2.438803 |
| Complete publication | 4.886221 | 4.827990 | 4.887209 | 4.841204 |
| Through process exit | 5.168815 | 5.136388 | 5.170594 | 5.150514 |

Both runs retained the original terminal and signed detector digests, the 116 ordered owner and role rows, the original regional result after 24 probes, the same numerical evidence digests and the complete 179-point grid. All eight PNGs matched the saved original encoded SHA-256 and independently decoded RGBA SHA-256. Each arm reproduced the existing position exactly. The error below is inherited from the sealed weak control at those identical positions. [Original position and RF evidence](live-orbit-setup-audit.md) · [Complete checks and figure digests](measurements/exact-phase-forecast.json)

| Calibration | Latitude, longitude | Horizontal error (km) | RF RMS (Hz) |
|---|---|---:|---:|
| `c = 0` | 37.838785686, −122.493087680 | 1.31105 | 121.52625 |
| Fitted `c` | 37.840030854, −122.501297265 | 1.69402 | 120.29086 |

Using the repeated effect as a credit in the earlier 0.394 s conditional gap still leaves roughly 0.35 s. That comparison uses audit `01932bb1d`, which assumed 2.400 s authenticated acquisition and unchanged rendering. There was one weak saved publication pair and no dense or raw timing for this change. The new component cases cover binary64 sigma, signed zeros and extremes, exact shared date preparation, reversed epochs and fresh propagations. They passed with the adjacent orbit, grid and Graph tests, 26 cases altogether. The prototype is confined to the research runner. [Weak recording budget](warm-recording-budget.md)

For a repeat on Gauss, use the existing pinned weak binding at `/dev/shm/leo-cumulative-grid-projection-01/weak-pair/binding.json` and the installed runner below. This binding and the inherited archive controls are live research inputs. The receipt includes their authorities and the source SHA-256s. Use a fresh output under tmpfs.

```sh
trial_dir="$PWD/reports/ALGO08/v3"
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial_tmp=$(sudo -n -u leo mktemp -d /dev/shm/leo-exact-forecast.XXXXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 sudo -n -u leo env \
  TMPDIR=/dev/shm OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$trial_dir:$PWD:$PWD/src:$release/src:$release" \
  "$release/venv/bin/python" -BPs "$trial_dir/exact_phase_forecast_trial.py" "$trial_tmp/run"
```
