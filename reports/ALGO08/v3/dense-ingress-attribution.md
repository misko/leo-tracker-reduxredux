# The dense short receiver spends most of its remaining acquisition CPU decoding and hashing

The two released-path controls used **400.27 and 399.75 ms** outside native receiver calls on the same authenticated 192-visit DS30-0008 prefix. Zstandard streaming reads and the two payload digest scopes used **335.41 and 335.72 ms**, about **84%** of that time. Batching the authenticated JSONL row validation raised its own clock in both orders. The measured ingress changes give no repeatable saving to carry into a raw publication. [Frozen protocol](dense-ingress-attribution-protocol.md) · [Complete CPU, authority and byte receipts](measurements/dense-ingress-attribution.json.gz)

## What the prefix measures

Both cases read the same three complete compressed members, **232,083,693 compressed bytes**, **307,200,000 decoded bytes**, and **518,249 index bytes**. All **56,663** compressed pages were resident at the start and end of all four arms of the two reversed pairs. The arms used the installed capped read hints and paired decoded SHA-256. Each issued 48 full and 336 shortened native lane calls. Timers surround the released functions. Compressed verification includes the descriptor, so the table subtracts that descriptor span before summing. The native and callback rows likewise use disjoint spans. The residual includes Python acquisition/reader orchestration, detection initialization, streaming context setup outside timed calls, and instrumentation. The seal following acquisition is outside the table.

| Disjoint stage | Original 1 CPU ms | Original 2 CPU ms |
|---|---:|---:|
| Compressed descriptor, transfer and buffer | 36.55 | 36.60 |
| Remaining compressed member authentication | 51.38 | 51.27 |
| Index member read and authentication | 0.62 | 0.64 |
| Index JSONL decoding and model validation | 2.14 | 2.07 |
| Zstandard streaming reads and returned bytes | 212.77 | 213.27 |
| Zstandard setup | 0.02 | 0.03 |
| Paired window/chunk decoded SHA-256 | 71.25 | 71.17 |
| Retune receipt JSON | 2.97 | 2.91 |
| Sample support gate | 0.47 | 0.43 |
| Detection and IQ authority digests | 0.88 | 0.89 |
| Callback outside native calls | 6.24 | 6.15 |
| Residual | 14.97 | 14.30 |
| Native receiver calls | 484.38 | 481.15 |
| **Acquisition** | **884.65** | **880.90** |

Batch parsing raised index decoding and validation from **2.14 to 2.35 ms** and from **2.07 to 2.38 ms**. It uses the same `splitlines` boundaries, parses each element in JSON mode through Pydantic `Json[model]`, and replays original per-line validation after batch validation failure. The measured span includes constructing the adapter once in each fresh batch process. Overall acquisition rose **5.49 ms** in the first pair and fell **9.46 ms** in the other. Native runtime itself moved **+5.34 and −6.04 ms**. The directly measured parser times give the relevant comparison at this scale.

All four arms reproduced the prior shorter-receiver detection packet byte for byte at SHA-256 `fa087af8dad3a919cad433aa23a44341d974fe5b85cfd0bfdc600f86c3fc089b`. This includes the same ordered probe rows, 195 signed selections and the same detection and raw authority. Each verified its three compressed and index SHA-256 values, all 192 decoded windows and all three complete decoded chunks. Tests exercise both published recording schemas, original validation error rethrow, and independently corrupted compressed, authenticated malformed index, wrong index digest, wrong window digest and wrong decoded member cases. The last window of the final member is outside the consumer scope and still carries its original validation. **21 component and adjacent tests passed.** [Reader bindings and batch prototype](dense_ingress_attribution.py) · [Tests](../../../tests/pipeline_eval/test_dense_ingress_attribution.py)

## What can affect the dense publication

The complete dense candidate used **32.403 CPU s** in acquisition. Native calls used **17.351 CPU s**, leaving **15.053 CPU s** in the acquisition scope. The recording used **67.352 CPU s** through process exit, and half of the historical same-recording installed ALGO08v3 control is **54.551 CPU s**. An ingress-only change would therefore have to remove **12.800 s**, or **85.0%** of the acquisition time outside native calls. Setting all 15.053 s to zero yields an unattainable mathematical floor of **52.299 CPU s** with every other span fixed. The complete elapsed gap to half of the historical run is **20.486 s**. The dense candidate started with **2.84%** payload residency. The restored prefix was resident and its results do not establish cold elapsed improvements. [Complete dense clocks and cache conditions](dense-full-short-raw.md)

For scale, extending the two control means by `6,772 / 192` would charge **7.514 CPU s** for current streaming reads, **4.322 s** for compressed and decoded digest work, **1.290 s** for the compressed descriptor, and **0.096 s** for reading, authenticating and validating the whole index. Under that illustrative rate, leaving both the original decoder and payload hash work intact would leave around **3.217 CPU s** of the observed 15.053 s pool. Other parts of the recording can differ in compression, the number of decoded bytes and kernel copy and fault costs. These are prefix-based estimates. The full recording supplied only the aggregate budget.

The recorded data require verification of the original compressed, per-window and full decoded contents. The prior checked allocation, tiling, and arena variants leave most of those costs intact. Removing streamed window allocation with reusable `readinto` had already failed to reduce the paired acquisition CPU; signed compressed-buffer pooling also failed to repeat. A direct read-only mapping of the original compressed file can still see another writer's updates or fault after truncation. The private experiment's XFS and the acquisition source are on the same `vg_bulk` filesystem with `reflink=0`, so a cheap copy-on-write snapshot for mapped verification was unavailable. The 212–213 ms scoped to Zstandard reads includes window materialization. No additional estimate of its allocator-only part or accounting of disk waits is possible from these controls. [Previous readinto controls](../single-core-2x/receiver-decoded-ingress.md) · [Compressed-buffer reuse](signed-ingress-reuse.md) · [Compressed digest tiling](../single-core-2x/compressed-digest-tiling.md)

## Reproduce

The receipt pins the authenticated input inventory and three members, the previous prefix output, runtime assets and experiment files. The private staging copy took 5.931 s elapsed before the four arms. One original arm reported 88 input blocks with its payload pages already resident. The other three reported zero. The run required no full raw replay or solve. [Attribution runner](dense_ingress_attribution_trial.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 90s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.dense_ingress_attribution_trial \
  run /srv/bulk/leo-dev "$short" "$fresh_output"
```
