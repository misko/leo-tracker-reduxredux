# Reusing the compressed destination in signed acquisition

Compressed-buffer reuse preserved the complete signed full-short detection packet. Its acquisition CPU fell from **1.236 to 1.137 s** in the first matched pair and rose from **0.993 to 1.016 s** in the reversed pair. The improvement did not repeat. [Frozen protocol](signed-ingress-reuse-protocol.md) · [Complete clocks and exactness receipt](measurements/signed-ingress-reuse.json.gz)

The complete DS30-0016 full-short acquisition used **3.426 CPU s**. Its measured native calls used **1.676 s**, leaving **1.750 s** for verified ingress, schedule and callback work outside the native calls, and assembly. Installed stock used **5.111 / 3.185 / 1.926 CPU s** at the same boundaries. The candidate's 12 ms native path already reads only its intended aperture, and the Python bridge passes 20 ms CI16 data by pointer. Reading only 12 ms from the Zstandard frame would remove original verified samples. [Physical raw-stage receipts](full-short-physical.md) · [Short-primary tail substitution control](mixed-aperture-receiver.md)

Earlier experiments already covered whole and overlapping decoded arenas, per-window decoded `readinto`, compressed read+hash tiling and next-member prefetch. The new variant retains the exact installed verified descriptor body and swaps its `np.empty` destination for two bounded reusable compressed buffers. Each readonly loan pins its exporter. A live decoder or retained derived buffer keeps its slot busy, so subsequent reads use the other slot or ordinary allocation. The Zstandard stream and paired decoded SHA routines, descriptor identity controls and immutable seal remain active. The prototype is scoped to the pinned synchronous reader. [Frozen protocol](signed-ingress-reuse-protocol.md) · [Previous compressed tiling](../single-core-2x/compressed-digest-tiling.md) · [Previous decoded arena](full-short-arena.md)

Even granting the whole **1.750 CPU s** outside the native calls for free, the observed candidate's **9.442 CPU s** process would still cost **7.693 s**. This gives an impossible ceiling of **1.227×** over that candidate or **1.475×** against the observed **11.347 CPU s** stock run on DS30-0016. The measured stock and candidate had different initial file residency. This CPU budget calculation holds the entire non-acquisition remainder fixed.

## Where the warm-prefix time went

| Matched order | Path | Descriptor CPU ms | Acquisition CPU / elapsed s | Acquisition through seal CPU / elapsed s | Minor faults |
|---|---|---:|---|---|---:|
| 1, first | Released | 375.1 | 1.236 / 1.256 | 1.240 / 2.566 | 62,833 |
| 1, second | Reuse | 298.1 | 1.137 / 1.137 | 1.140 / 3.680 | 43,935 |
| 2, first | Reuse | 183.1 | 1.016 / 1.018 | 1.019 / 3.633 | 41,890 |
| 2, second | Released | 148.8 | 0.993 / 0.993 | 0.996 / 4.064 | 20,410 |

The allocator allocated twice and reused one destination in both proposed runs, with no fallback or measurable change in peak RSS on this sample. The first pair's 77.0 ms descriptor gain reversed to a 34.3 ms loss in the second pair. Both timings include verified descriptor work and data transfer, so they do not identify a standalone allocation cost. The four runs each began and ended with all **56,663** payload pages resident. Three charged zero input blocks, and the first control charged 56 blocks. The seal and readback after acquisition took **1.310–3.071 s elapsed** and changed the apparent timing order. The test supplies no cold-input or whole-publication timing.

Across the four disjoint stage breakdowns, the compressed member check after subtracting the descriptor took **51.2–51.9 ms CPU**. The installed Zstandard stream and returned window bytes cost **212.1–214.2 ms**, paired decoded SHA cost **71.1–71.5 ms**, and the index member read and authentication cost **0.6–0.9 ms**. The 384 native calls used **473.4–487.4 ms**, the surrounding callback used another **5.7–6.9 ms**, and **18.6–28.1 ms** remained for untimed work and instrumentation. These clocks do not split actual decoding from constructing the returned Python bytes. [Per-stage counters](measurements/signed-ingress-reuse.json.gz)

All four runs verified all six compressed and index members, all 192 individual decoded digests and all three complete decoded member digests. They reproduced the prior full-short detection SHA-256, including the raw authority, 384 ordered probe rows, and 195 signed selections. The 18 component and adjacent tests include retained views, fallback allocations and inconsistent compressed, index, window, and decoded-member bindings. [Component tests](../../../tests/pipeline_eval/test_signed_ingress_reuse.py)

## Reproduce

The test stages only the original first three signed DS30-0008 members using the existing authenticated private copy and processes 192 opportunities. The coordinator reads the checkout's audit packages. Workers verify installed source digests and use the installed storage runtime and native detector assets. The successful staging copy took 24.074 s elapsed outside the four measured acquisition intervals. Earlier setup attempts stopped before a timed visit because of the module path and differences between the installed and checkout reader binding. No full recording or positioning run is needed. [Trial runner](signed_ingress_reuse_trial.py) · [Compressed buffer and stage timings](signed_ingress_reuse.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.signed_ingress_reuse_trial \
  run /srv/bulk/leo-dev "$short" "$fresh_output"
```
