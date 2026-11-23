# Full-aperture confirmation of prospective short observations

Full-aperture confirmation recovered the two-arm development result on **DS30-0057**, where it reduced the unconfirmed repair's error from **0.708 / 0.937 km to 0.440 / 0.703 km**. It also removed observations that had improved the weak **DS30-0016** fix, leaving fitted error **358 m above** installed ALGO08v3. That exceeds the 250 m limit by 108 m. The algorithm retained every original owner in both cases. The weak-case failure and the estimated receiver work stop this route before public simulations or raw replay. [Frozen protocol](full-confirmed-future-protocol.md) · [Scored receipts](measurements/full-confirmed-future.json.gz)

## What the confirmation changes

The original short packet supplies the forward graph, existing owner labels, and forward and reverse temporal support. The gate touches only future-only factors from scheduled 12 ms slots. A same-lane 20 ms rank-zero selection from the installed packet must agree within two wrapped samples and 250 Hz of signed CFO. Earlier scheduled 20 ms factors are already full-aperture evidence and stay eligible. Every accepted row retains its original signed short value and observation identity. The protected repair retains the original graph and runs the same Doppler, ambiguity, compatibility and rollback decisions in both calibration arms. The selector uses no reference coordinates or installed satellite owners. [Selector and solver binding](full_confirmed_future.py) · [Existing match predicate](short_primary_epoch_audit.py)

| Case | Future-only rows | Already full | Short matching / candidates | Kept for repair | Added owners per arm, unconfirmed → confirmed |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 69 | 16 | 12 / 53 | 28 | 9 → 4 |
| DS30-0057 | 225 | 43 | 64 / 182 | 107 | 138 → 59 |

The confirmed repair added two already-full and two matched-short rows on DS30-0016, and 23 already-full and 36 matched-short rows on DS30-0057. Of the rejected short candidates, **35 / 69** had no full-packet selection and **4 / 31** had a full-packet selection of residual rank, in case order. The other **2 / 18** missed the measurement tolerances. The installed saved packet contains only the continued selection for each lane. A missing factor there can reflect either full-aperture detection or continuation. The reported coverage is against that persisted packet. [Admission and readback receipts](measurements/full-confirmed-future.json.gz)

## Position, frequency and published evidence

All four arms of comparison completed on each recording. The scorer decoded all **64 figures** and verified their stored bytes and pixel digests. All grids completed at 179 points with zero endpoint objective replay difference. Both repaired arms preserved the same 107 forward owners on DS30-0016 and 1,220 on DS30-0057, including satellite and conditional or predictive role. The two recordings are development controls from the same physical site. [Image, path, grid and owner evidence](measurements/full-confirmed-future.json.gz)

| Case and method | Horizontal error, `c = 0` / fitted (km) | RF RMS, `c = 0` / fitted (Hz) |
|---|---:|---:|
| DS30-0016 installed v3 | 1.644 / 1.661 | 109.38 / 109.48 |
| DS30-0016 forward only | 2.473 / 2.542 | 115.88 / 115.36 |
| DS30-0016 unconfirmed repair | 1.479 / 1.849 | 121.19 / 119.95 |
| DS30-0016 confirmed repair | **1.730 / 2.019** | **120.93 / 119.90** |
| DS30-0057 installed v3 | 0.426 / 0.525 | 109.97 / 109.83 |
| DS30-0057 forward only | 0.378 / 0.641 | 120.22 / 120.25 |
| DS30-0057 unconfirmed repair | 0.708 / 0.937 | 121.28 / 121.31 |
| DS30-0057 confirmed repair | **0.440 / 0.703** | **120.58 / 120.68** |

The confirmed DS30-0057 was still about 62 m farther from the reference than the forward-only fix in each arm. On DS30-0016 fitted `c` lowered confirmed RF RMS by 1.03 Hz while increasing error by 289 m. On DS30-0057 fitted `c` increased both RF RMS and error. The frequency and location changes are separate measurements. [Fixed physical references](../../2026_11_21_ds30_full/reference-audit.json) · [Exact scores](measurements/full-confirmed-future.json.gz)

## Receiver work implied by the saved oracle

The installed detector can choose a second factor or withhold the current leading factor based on same-receiver/RF history. It keeps up to 12 admitted observations and uses their full factor vectors inside eight seconds. A targeted 20 ms native callback alone would leave that state unknown. The signed mixed receiver stores its chosen factor only, even on scheduled full windows. Charging same-lane context means rerunning the union of the relevant current and prior opportunities, whether those callbacks return zero, one or two factors. Retaining raw full vectors during the first pass would avoid some of those later callbacks. The deterministic native callback state was not qualified for out-of-order use, so invoking the original stock receiver from its beginning through the last needed target is the conservative exact-replay plan. It retains ordinary authenticated input authority. [Original continuation implementation](../../../tools/pipeline_eval/variants/carrier_continuation.py) · [History counts and receipts](measurements/full-confirmed-future.json.gz)

| Planned work | DS30-0016 | DS30-0057 |
|---|---:|---:|
| Requested short target lanes / stereo visits | 53 / 47 | 182 / 166 |
| Target and prior-timeline lanes / stereo visits | 280 / 244 | 1,109 / 943 |
| Stereo visits with retained first-pass full vectors | 213 | 826 |
| Original prefix through last target, admitted stereo visits | 636 / 713 | 2,256 / 2,304 |
| Decoded stereo bytes, history union / full prefix | 390 MB / 1.018 GB | 1.509 GB / 3.610 GB |
| Upper envelope for retaining all admitted stereo windows | 1.141 GB | 3.686 GB |

Targets are known after reverse continuation. A second sequential read would traverse nearly the whole admitted prefix and would still need the compressed and decoded input checks. The observed compressed input pages represented 0.992 GB and 3.347 GB across the two full recordings. Sparse reread of exact chunks was neither implemented nor timed. The history-union byte counts are stereo payload sizes and omit decoder storage, container metadata and other scratch buffers. [Recorded input and archive authority](measurements/full-confirmed-future.json.gz)

The previously measured full native mean was 4.47 ms per stereo visit on DS30-0016 and 4.96 ms on the earlier DS30-0057 mixed receiver's full slots. At those rates the isolated targets add **0.210 / 0.824 CPU s**. The history-union estimate rises to **1.090 / 4.679 s**, or **0.951 / 4.099 s** if the first pass retains full vectors from its existing anchors. The conservative full-prefix estimate is **2.841 / 11.194 s** of extra native CPU, excluding input and setup. These are callback cost projections, not measurements of elapsed replay. Scientific selection against the saved packet cost 3.3 / 8.5 ms. The confirmed fresh saved-input workers took 5.482 / 9.874 CPU s (5.484 / 9.888 elapsed), including both calibrated fits, grid and figure round trips. [Weak original clocks](measurements/weak-combined-raw.json) · [DS30-0057 original clocks and callback counts](measurements/short-raw-diagnostic.json) · [Confirmed clocks](measurements/full-confirmed-future.json.gz)

The weak saved worker alone exceeded half of the measured 10.831-second complete v3 raw run. For DS30-0057 an older complete v3 run used 30.753 CPU s. Half is 15.377 s. The saved worker plus only the prior mixed detector's native CPU and the isolated-target estimate totals 16.178 s on that scale, before charging native predecessor callbacks, input traversal or buffering. These are planning comparisons across process boundaries. The fresh DS30-0057 stock run had an archived terminal but timed out during PNG synchronization. The crossover has no measured raw-to-exit speed ratio. [Archived complete stage clocks](first-55/stage-clocks.csv) · [Fresh stock censoring](short-raw-diagnostic.md)

## Reproduction

Run the worker against the installed payload and the scorer with the checkout's science modules first, using the shared Gauss lock, CPU 2, nice 15, I/O priority 7, one numerical thread and the recording-readable `leo` account. The saved-input path does not open I/Q. The first two worker attempts stopped before inference because the wrapper initialized lazy imports before the installed runner's own initialization. The successful attempts deferred the archive/packet binding until the runner's preparation callback. Nine focused tests passed. The decompressed aggregate SHA-256 is `2ee148218cf8db407c7bdc07cdf615528fe9aefad04c8ac9374d490acd1dfa81`. [Tests](../../../tests/pipeline_eval/test_full_confirmed_future.py) · [Runner](full_confirmed_future.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
driver="$PWD/reports/ALGO08/v3/full_confirmed_future.py"
slot() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n15 ionice -c2 -n7 taskset -c 2 \
    timeout 110s sudo -n -u leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
slot PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  "$release/venv/bin/python" -BPs "$driver" trial "$case" "$new_output"
slot PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD:$payload:$release" \
  "$release/venv/bin/python" -BPs "$driver" score "$case" "$new_output" --receipt "$new_receipt"
```
