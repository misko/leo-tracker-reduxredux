# Direct I/O saves descriptor CPU on one dense member

Linux direct I/O reduced compressed-descriptor CPU by **5.62–7.88 ms** on one authenticated DS30-0008 member. Complete acquisition elapsed moved from **766.74 to 762.44 ms** and from **308.89 to 309.05 ms** in reversed orders. This missed the frozen requirement for repeatable acquisition elapsed savings. Both direct arms bypassed the file-page cache and every arm returned the same signed detection file. [Frozen protocol](dense-direct-cold-protocol.md) · [Complete measurement receipt](measurements/dense-direct-cold.json.gz)

## Matched signed reads

The test staged one owner-private XFS copy of the manifest, first complete index and first **77,442,779-byte** compressed member. All four arms started with zero of the **18,907** compressed pages resident. Only the temporary payload inode received cache advice. Buffered arms finished with all pages resident. Direct arms finished with zero. Both direct arms issued one actual aligned `preadv` for a rounded **77,443,072-byte** output buffer. XFS reported **512-byte** memory and offset alignment. The result lent exactly the original compressed length to the standard checker. Both variants then ran the same Zstandard decoder and issued 16 full and 112 short native lane calls.

| Pair order | Read path | Descriptor CPU ms | Descriptor elapsed ms | Compressed MB/s in descriptor | Acquisition CPU ms | Acquisition elapsed ms | Input blocks | Final payload pages |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1, first | Buffered | 29.108 | 460.404 | 168.2 | 332.959 | 766.739 | 151,272 | 18,907 |
| 1, second | Direct | 21.226 | 479.880 | 161.4 | 300.476 | 762.443 | 151,256 | 0 |
| 2, first | Direct | 19.109 | 20.127 | 3,847.8 | 307.911 | 309.051 | 151,256 | 0 |
| 2, second | Buffered | 24.734 | 25.119 | 3,083.0 | 308.356 | 308.886 | 151,272 | 18,907 |

The measured scope charged **77,451,264 bytes** of process input in each buffered arm and **77,443,072 bytes** in each direct arm. These kernel counters cover the unchanged acquisition and seal scopes. The descriptor elapsed-minus-CPU spans were **431.30 / 458.65 ms** in pair one and **0.39 / 1.02 ms** in pair two for buffered/direct. The large swing between pairs persisted with the same observed file-page state and byte counts. The storage tiers below file pages and device queues were uncontrolled. The complete acquisition CPU outside native detection decreased **12.65 ms** and **2.97 ms**. Native detection CPU itself differed by **−19.83 ms** and **+2.53 ms**. Through-seal elapsed varied further from **1.429 to 7.098 s** and is outside the acquisition comparison. Private staging took **9.940 s** before the arms. Per-arm page reset and observation took **0.05–2.11 ms** before timed worker launch. [Scoped runner](dense_direct_cold_trial.py)

## Compression and input authority

The private direct adapter opens the member with no symlink following and checks the descriptor type, link count and size bound before reading. It allocates an anonymous aligned buffer, handles aligned short reads, rejects premature EOF or changes in device, inode, link count, size, mtime or ctime during the read, and lends an owned read-only view of exactly the original data. The final read can return the non-aligned EOF length. Capability failures use the released buffered descriptor path. All measured direct reads succeeded without this fallback. The adapter applies only to the single staged private member. The existing reader checks the authenticated manifest, compressed and index hashes, every window IQ hash, and the full decoded-member hash in either mode. [Adapter](dense_direct_cold.py)

All four outputs matched signed detection SHA-256 `856affd89c8d3effd46c766efd9d02919c14641ad6b9837f3dc685f9f757ba2e`, which includes the earlier 64-visit result's original authority, 128 ordered probes, and 67 selected signed factors. Its 64 decoded window digests and original member and index hashes also match the previous independent prefix. Synthetic controls cover non-aligned EOF, continuing aligned short reads, failed capability, early EOF, file growth and mutation, symlinks, hardlinks, size bounds and original digest checks. **20 component and adjacent tests passed.** [Previous signed member](dense-zstd-backend.md) · [Tests](../../../tests/pipeline_eval/test_dense_direct_cold.py)

## Complete dense elapsed budget

Repeating the measured descriptor CPU savings at the same local rate over all **6,772 issued visits** would save **0.60–0.83 CPU s**. The complete raw candidate previously needed **20.486 s** of additional elapsed savings to reach half the historical control. The entire measured acquisition elapsed-minus-CPU difference was **28.046 s**. An ingress change drawing solely from that span would have to remove about **73%** of it with other spans held fixed. This experiment measured no reliable wait reduction. Its cold condition concerns only the private inode's file pages. A warm-aware fallback remains unmeasured and the prescribed comparison covered only one member. [Complete raw clocks](dense-full-short-raw.md)

## Reproduce

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 90s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.dense_direct_cold_trial \
  run /srv/bulk/leo-dev "$short" "$fresh_output"
```
