# Full-short prefetch on two cold private physical members

One-member prefetch reduced measured acquisition elapsed from **1,693.34 to 688.46 ms** in the first order and from **645.16 to 623.14 ms** in reverse. The advice arm's demand descriptor spans swung from **1,112.95 to 51.20 ms** with identical file-cache states and process input bytes. That variation prevents assigning the first pair's large elapsed change to prefetch. The candidate reached **224.74 and 248.29 compressed MB/s**, below the frozen **250 MB/s** prefix threshold in both orders. The faster run missed it by **4.25 ms**. [Frozen protocol at `f498ed021`](physical-short-prefetch-protocol.md) · [Measurement receipt](measurements/physical-short-prefetch.json.gz)

| Pair order | Compressed read path | Acquisition CPU ms | Acquisition elapsed ms | Elapsed minus CPU ms | Compressed / decoded MB/s | Launch to exit s | Peak RSS MiB |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Released advice | 628.05 | 1,693.34 | 1,065.29 | 91.37 / 120.94 | 3.573 | 402.57 |
| 1 | One-member prefetch | 643.23 | 688.46 | 45.23 | 224.74 / 297.48 | 2.670 | 402.53 |
| 2 | One-member prefetch | 622.09 | 623.14 | 1.05 | 248.29 / 328.66 | 2.571 | 402.51 |
| 2 | Released advice | 642.66 | 645.16 | 2.51 | 239.82 / 317.44 | 2.519 | 402.48 |

## Worker and descriptor scopes

Both prefetch arms lent the complete **77,279,318-byte** next member, each with one hit and zero fallbacks. The worker took **25.23 and 25.45 ms CPU**, included in the process acquisition totals, and **156.71 and 53.18 ms elapsed**. Demand waited **9.10 and 8.01 µs**. The advice arm submitted one **16 MiB** hint per run. Both workers inherited CPU 2. Their measured CPU can appear in nested process-time measurements around callbacks as well. The first pair changed total acquisition CPU by **+15.18 ms** and the second by **−20.57 ms**. The second pair's **22.02 ms** acquisition elapsed decrease includes only **1.45 ms** of elapsed-minus-CPU decrease. Launch-to-exit elapsed in the second pair favored advice by about **52 ms**. It includes fresh interpreter and recipe validation. Each immutable acquisition seal took under **1.8 ms**. [Runner](physical_short_prefetch.py)

The candidate and control used the same first two DS30-0008 members and fresh acquisition children. The recordings contain **154,722,097 compressed and 204,800,000 decoded bytes**. Each pass started with zero compressed file pages and finished fully resident, with both indexes fully resident throughout. Every arm charged **154,726,400 input bytes** and **302,200 input blocks**, including the helper. The tests reused the prior owner-private XFS copy with zero original-source payload re-reads, zero additional staging bytes and no cache advice on original files. Linux file-cache cold does not establish the state of device caches or queues. [Descriptor and verification ladder](physical-stage-envelope.md)

## Output and input authority

All arms used the same released descriptor and decoder, paired SHA-256, original signed manifest, exact visit and delivery metadata and full output agreement. Each completed **32** 20 ms and **224** 12 ms native calls, verified all original indexes, compressed and decoded members and 128 per-window hashes, and produced exactly **136 factors**. All **256** original probe rows match the existing complete raw candidate. The scoped sealed packet is byte-identical across all four arms with SHA-256 `434442ef8872e0d87f9f94081d072f072b71f5bf7a023773f05949d1f7d6417f`. This compares acquisition only. One prefix records little of the variable storage service, CSI and scheduling that determine the full recording's elapsed time. [Prior complete dense publication](dense-full-short-raw.md) · [Original resident simulation control](public-short-prefetch.md)

## Reproduction

Use a healthy private XFS replica from the ladder. The measured copy is retained at `/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt`. The runner checks the original inventory and manifest bindings in its `recovered-request.json` and writes fresh outputs to tmpfs. Three component and 27 adjacent tests passed.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 timeout -k 4s 75s \
  env PYTHONPATH="$PWD:$release/src:$release:$payload" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.physical_short_prefetch \
  run "$private_replica" "$short" /dev/shm/physical-short-prefetch-reproduction
```
