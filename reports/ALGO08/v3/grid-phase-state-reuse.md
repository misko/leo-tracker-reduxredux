# Reuse exact predictive orbit states across numerical grid points

On the genuine DS30-0008 short-receiver grid with the installed graph, reusing position-independent interpolation reduced predictive geometry from **0.441 to 0.228 CPU seconds**, a saving of **0.213 seconds**. The released curved likelihood already reused its interpolated states. Its 356 fresh curved calls performed zero interpolation during the grid. The installed checked-posterior handoff still used unprepared predictive geometry at every point. Reusing the existing phase cache there preserved every returned array and its layout bit for bit in all 356 calls. It also preserved the original 179-point grid and both calibration arms. [Frozen protocol](grid-phase-state-reuse-protocol.md) · [Per-point timings and scientific checks](measurements/grid-phase-state-reuse.json.gz)

| Predictive work across 178 fresh locations in each arm | Released | Cached |
|---|---:|---:|
| Geometry CPU s, including cache creation | 0.440928 | 0.227863 |
| Interpolation CPU s within geometry | 0.218918 | 0.000979 |
| Interpolation calls | 1,780 | 8 |
| Interpolated position and velocity rows | 1,759,352 | 8,472 |

Each arm has a private view of 706 predictive observations. The unprepared projector interpolates the nominal states twice, both ±0.01-second states once, and the three physical mode states once per observation. The existing cache builds the nominal states once for the receiver projection and physical mode derivative. It also keeps the two offset states and all three sets of mode states. The candidate uses the same original receiver-dependent operations and assembles features anew in the original row and column layout. The cache checks the orbit-buffer identities and exact time, label and phase-reference bytes. It accepts the existing fixed orbit-bank contract, where a new bank replaces the buffers. Nonzero observer altitude keeps the released path. No state crosses calibration arms. [Measured geometry helper](grid_phase_state_reuse.py) · [Component tests](../../../tests/pipeline_eval/test_grid_phase_state_reuse.py)

This boundary differs from the earlier predictive-layout trial, which prepared the older predictive attachment and changed its dense Gram and column scaffolds. The installed checked handoff obtains the curved posterior directly and still calls the released `geometry_features`. The candidate changes interpolation alone within that call. Exact cross-arm projection reuse would need matching phase-interpolated states, and the earlier robust warm-start experiments changed objectives and sometimes branch evidence. This test kept the original cold Gamma iteration, native sparse posterior, reduced predictive algebra, accepted held points and all original grid coordinates. [Predictive layout](../single-core-2x/solver-predictive-layout.md) · [Cross-arm ceiling](../single-core-2x/solver-grid-cross-arm.md) · [Robust rate experiments](../single-core-2x/solver-robust-updates.md)

The paired geometry runs shared one genuine solve, one robust curved posterior per fresh arm and point, and one predictive integration. The grid took 5.843 CPU seconds with both geometry calls and the verification instrumentation. The measured curved evaluation and posterior export took 3.935 seconds, the reduced predictive integration 1.122, and the posterior checks 0.023. The paired geometry order alternated globally and usually followed the sampler's fixed arm interleave. This balances aggregate call order and leaves the individual arm timing effects confounded with order. The original matched publication evidence took 6.133 CPU seconds. The 0.213-second local saving represents about 3.5% of that evidence clock and 0.83% of the archived 25.566-second saved solve. This is a stage scale comparison. The instrumented replay does not establish a complete solve speedup. [Matched saved control](dense-full-short-crossover.md)

Both fixed-zero and fitted `c` kept the original 4,367 owner and role rows, RF RMS of 140.961 / 140.950 Hz, positions, sampled minima, grid and path digests, and zero endpoint replay error. The early proof, catalogue decisions and signed final route match the archived receipt. The study ended after this one grid. No raw acquisition or PNG rendering ran. Sixteen focused tests passed. [Numerical replay wrapper](grid_phase_state_trial.py)

## Reproduce

Give `grid_phase_state_trial.py` a fresh output directory under the shared lock described below. The runner uses the original authenticated dense native packet, causal archive, historical raw-launch verifier and saved numerical comparator. `replay.json` contains the audited scientific replay and `grid-audit.json` contains the per-call timing and exactness comparisons. The original `grid-audit.json` SHA-256 is `e5a4047b7d1eea818bffe19b72313e9af7861bfb2d1d59a94a28e235fff912e8`.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/leo-grid-phase-state.XXXXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$PWD:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/grid_phase_state_trial.py "$out/trial"
```
