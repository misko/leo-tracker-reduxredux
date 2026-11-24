# Three exact solver options on saved physical DS30-0057

One complete DS30-0057 saved publication with the duplicate Graph check, portable catalogue and grouped exact rank took **9.862 CPU seconds and 10.011 elapsed seconds through exit**. The archived same-packet control took **9.869 CPU seconds and 9.964 elapsed seconds**. All three options activated and reproduced the scientific outputs. The 7 ms CPU difference and 47 ms elapsed increase do not establish a speed gain across these separate launches. [Frozen protocol](exact-solver-0057-protocol.md) · [Complete receipt](measurements/exact-solver-0057.json.gz) · [Same-packet control](cumulative-phase-forecast-DS30-0057.md)

| Saved boundary | Original matched control | Exact combination |
|---|---:|---:|
| Numerical solve CPU / elapsed | 6.440 / 6.442 s | 6.430 / 6.430 s |
| Complete publication CPU / elapsed | 9.621 / 9.715 s | 9.586 / 9.735 s |
| Fresh process CPU / elapsed through exit | 9.869 / 9.964 s | 9.862 / 10.011 s |
| Process input blocks / major faults | 3,336 / 0 | 296 / 0 |

The duplicate check removed **3 proposals in 16 lane finalizations**, with 0.253 ms CPU spent checking. The grouped rank used all 624 compact curve calls with zero full fallback, removing **973,322 of 1,002,768** requested row profiles. Stock-shape bias multiplication still processed 34,942,608 cells. The inclusive rank cost 1.107 CPU s, and its separately charged six-node receipt took 14.5 ms CPU. The prior same-packet solve has no isolated rank clock for direct comparison. The portable metadata from earlier DS30-0008 hit **16 of 26** eligible body digests and attached 179,121 rows. Ten bodies took the ordinary path, with zero invalid hits and zero regional preparation fallback. Charged active preparation was 1.810 CPU s, including the artifact load, 112 ordinary verified archive reads and 26 strict body reparses. The complete run recorded 294,237 native strict validations across 28 catalogues with zero fallback. [Rank and preparation audits](measurements/exact-solver-0057.json.gz)

The original signed inventory contained 2,717 issued visits, of which 2,304 were admitted to the unfiltered mixed 20/12 ms receiver. Both publications used the same saved packet, recorded authority, original supplied offer and causal cutoff. The unchanged regional result evaluated all 25 probes over six source digests with the `inside_score` stop, six native blocks and one scalar position. The terminal, both fits, 1,542 ordered owners and roles per calibration, 179 matched grid points and the optimizer path were identical. All eight PNGs matched the original encoded bytes and decoded pixels, and the grid and path both bind the verified position PNG. [Verification and source identities](measurements/exact-solver-0057.json.gz)

| Calibration | Horizontal error, both runs | RF RMS, both runs |
|---|---:|---:|
| `c = 0` | 240.228 m | 125.297918 Hz |
| Fitted `c` | 296.935 m | 125.310558 Hz |

All 49 original archive names, timestamps, body hashes and lengths were resolved to existing tmpfs files. The private hard-link view preserved the whole inventory digest. All 21,413 pages were resident on admission. No original backing catalogue bytes were copied, and the paid solver verified every catalogue it read. There were no waveform calls. Only one new candidate was timed on the shared Gauss CPU 2 slot, at nice 15, best-effort I/O 7 and one numerical thread. The previous control ran at a different time and had a different cache profile. [Archive custody](measurements/exact-solver-0057.json.gz)

A launcher import-order error stopped before the worker launched. The completed worker was never repeated. Postscore verification corrected for two versions of the archived control receipt and used the read-only repository storage interface. Fifteen component and adjacent tests passed. The uncompressed receipt SHA-256 is `621db1154873ac24ce68b2c0bdc128dc5a6bff2f67166cb78455ac06b2342eec`. The measured worker was frozen in `55db86e56` with driver source SHA-256 `d5961c13d1911bbfbba62fa3fc6028ed259e5cab9802d48914d46a931eca3a9e`. Subsequent driver edits affect verification only. [Runner](exact_solver_0057.py) · [Tests](../../../tests/pipeline_eval/test_exact_solver_0057.py)

```sh
study=/dev/shm/leo-v3-exact-solver-0057
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
output=/dev/shm/leo-exact-solver-0057-replay

sudo -n -u leo flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$study:$study/reports/ALGO08/v3:$release/src:$release:$payload" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$study/reports/ALGO08/v3/exact_solver_0057.py" run "$output"
```

After the process clock seals, use the same command with `verify` and prefix `$study/src:` to `PYTHONPATH` for the read-only scoring interface.
