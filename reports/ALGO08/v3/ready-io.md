# Ready signed receiver work during original DS30 input waits

The signed receiver used **336.37–336.57 ms of CPU** while two next-member `readv` calls were outstanding. Reader `D` samples bracketed **311.49 ms** of that work, including **301.14 ms** bracketed by `folio_wait_bit_common` in the same read. Scoring advanced while the worker encountered page waits, with individual sleep, wake and scheduling events unresolved between samples. The bounded prefetch already delivered this overlap. The **451.60 ms** the caller still waited for the buffers is a ceiling for additional overlap, with ready work at that boundary unestablished. [Common-clock trace and receipt](measurements/ready-io-DS30-0008.json.gz)

| Member prefetched | Compressed bytes | Worker readv elapsed / CPU (ms) | Previous-member receiver CPU during readv (ms) | CPU bracketed by folio waits (ms) |
| --- | ---: | ---: | ---: | ---: |
| `iq-000001.ci16.zst` | 77,279,318 | 423.69 / 24.18 | 168.93 | 149.19 |
| `iq-000002.ci16.zst` | 77,361,596 | 742.18 / 23.27 | 167.45–167.65 | 151.95 |

The existing signed raw and storage receipts have aggregate stage clocks, cache residency and charged reads. They lack a common-clock dependency trace. This single probe used the first three original signed DS30-0008 members in place, with no staging copy, cache advice or eviction. At launch Linux `cachestat` found zero of **56,663** payload pages resident. All were resident afterward. The acquisition took **2.121 s elapsed and 0.918 s process CPU**, charged **455,032 filesystem input blocks**, and recorded **232,976,384 bytes** read in `/proc/self/io`. The worker returned both whole buffers without fallback, totaling **154,640,914 bytes**. The two reads above cover only those speculative buffers. The first member was a demand read. [Existing dense raw clocks](dense-full-short-raw.md) · [Original input timing](dense-ingress-attribution.md) · [Measured trace](measurements/ready-io-DS30-0008.json.gz)

The trace uses a common monotonic wall clock for each worker syscall and each chronological main-thread scoring callback, plus a separate CPU clock per thread. For each callback, the lower bound subtracts the maximum CPU that could fit outside outstanding reads. The upper bound is the smaller of callback CPU and overlapping elapsed time. There were 245 `D` observations in 255 active syscall samples, including 238 named folio waits and seven with an unavailable wait channel. The remaining ten were runnable observations. The read's elapsed time outside worker CPU can include storage waits, runnable delays and other stalls. [Analysis and instrumentation](ready_io.py)

### Where additional work could come from

The same reader already decodes and verifies the previous member's windows and scores admitted visits while the next compressed member is loading. Once the caller reaches demand, the next member's bytes and its authenticated windows are prerequisites for further scoring. The **451.60 ms** in `Future.result()` measures exposed caller wait in these two transitions. It gives only a ceiling for any schedule limited to those waits, with ready receiver work already consumed. With the current queue, the trace identifies no extra receiver work at demand. A deeper queue or access to partial compressed data would need its own dependency, memory and verification evidence. [Reader and scheduler path](../../../tools/pipeline_eval/variants/experimental/receiver_member_prefetch.py) · [Trace](measurements/ready-io-DS30-0008.json.gz)

The authenticated first-window clock fixes the causal cutoff early. Selection and parsing of cutoff-eligible TLE snapshots are therefore candidates to move once their inputs are available. This run did not read or parse those snapshots, so their CPU cost, residency and availability during either wait are unestablished. Per-probe preprocessing can use verified visit metadata and the clock anchor, but its exact reusable fraction was not measured. The current Graph path fits complete RF lanes. The orbit bank uses the finished tracks' duration, and the noise, previous-orbit history, solver and grid use the complete prepared packet. Credit none of those work items toward additional overlap based on this prefix. [Probe timing and cutoff](../../../src/leo/analysis/glrt_frequency_input.py) · [Graph preparation](../../../src/leo/analysis/localization_v3/tracks.py) · [Causal sky and duration](../../../src/leo/operations/localization_v3_inputs.py) · [Solver preparation](../../../src/leo/application/localization_v3.py)

### Integrity and reproduction

The released reader retained the three compressed and three index member seals, all **192 per-window** decoded digests, and all **three whole-decoded-member** checks. The prefix contained **232,083,693 compressed bytes**, **518,249 index bytes** and **307,200,000 decoded bytes**. The generated document matched the archived signed full-short prefix byte for byte at SHA-256 `fa087af8dad3a919cad433aa23a44341d974fe5b85cfd0bfdc600f86c3fc089b`. It contains 384 ordered probe rows and 195 selected factors. The raw authority and detector manifest were recomputed from the frozen inventory and observed ordered windows. The trace pins all member sizes and digests, and the original signed route verifies its released runtime and native assets. No solver, calibration fit, geographic output or whole-recording speedup was measured. Twenty-eight component and adjacent tests passed. [Frozen signed prefix](signed-ingress-reuse.md) · [Arithmetic-bound tests](../../../tests/pipeline_eval/test_ready_io.py) · [Receipt](measurements/ready-io-DS30-0008.json.gz)

The measured runner is at `a796cb3f`. Run under the normal read-only Gauss recording account with a fresh tmpfs output directory. The original receipt is retained at `/dev/shm/leo-v3-ready-io-original-0008/receipt.json` and has SHA-256 `9fe3372bab0513edc6947c31c37270d3821ddf733f7da58b79459107cda5a34d`.

```sh
repo=/dev/shm/leo-v3-ready-io-sparse
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
output=/dev/shm/leo-v3-ready-io-replay

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env PYTHONPATH="$repo:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/timeout 30s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.ready_io "$output" "$short"
```
