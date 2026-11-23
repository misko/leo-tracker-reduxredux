# A seekable authenticated sidecar for one physical DS30 member

On one original DS30-0008 member, the private seekable format saved **53.90–70.03 CPU ms** for the mixed 20/12 ms receiver and added **31.79–37.72 CPU ms** for the all-20 ms named receiver. Both modes reproduced their original ordered probes exactly. Creation and independent complete readback cost **473.20 CPU ms** before the first subsequent analysis. At the two-order mean, mixed analyses break even on analysis **8**, or **10** when charging the separate cache-only staging copy. The all-20 ms pass has no crossover at these measured rates. [Physical receipt](measurements/seekable-member-DS30-0008.json)

| Authenticated analysis | Original CPU / elapsed ms, orders 1 and 2 | Seekable CPU / elapsed ms, orders 1 and 2 | Original / seekable compressed bytes | Original / seekable decoded bytes |
| --- | ---: | ---: | ---: | ---: |
| Mixed, 8 full plus 56 short | 316.444 / 319.126, 298.042 / 298.068 | 246.415 / 246.436, 244.145 / 244.159 | 77,442,779 / 50,350,044 | 102,400,000 / 66,560,000 |
| Named, all 64 full | 478.204 / 478.214, 482.821 / 482.862 | 515.926 / 515.968, 514.616 / 514.674 | 77,442,779 / 77,440,162 | 102,400,000 / 102,400,000 |

Mixed elapsed time fell by **72.69 and 53.91 ms**. Order 1 ran the original first and order 2 ran the sidecar first, all within one process. Each timed arm opened a fresh reader and fresh receiver contexts. The timings include metadata verification, decoder work, full eligibility checks and the matching real pinned native callbacks. The mixed pass returned 128 probes and 67 factors with either reader. The named pass returned 128 probes and 19 factors. Distinct receiver recipes account for the different factor counts. The original used the installed compressed buffer and paired decoded SHA-256. Both formats ran in tmpfs. Logical byte counts describe files read by the application, with no estimate of cold block-device readahead. [Ordered probes and stage counters](measurements/seekable-member-DS30-0008.json)

### Commitments and read coverage

The private sidecar stores two level-1 Zstandard streams as separate ordered files. The prefix file contains one independent 12 ms stereo CI16 frame per visit. The tail file contains the corresponding independent 8 ms frame. Detached SHA-256 of the seek table binds the original manifest and index, visit ordinal, exact frame extents and SHA-256 of both the encoded and decoded bytes. The trial uses the root pinned outside the sidecar in the result receipt. A future capture would need to sign or externally pin that root when recording seals. Mode `0400` and stable descriptor metadata protect the private trial's readback, and digest verification rejects changed bytes. [Private reader and writer](seekable_member.py)

Conversion exhausts the original verified reader before writing the new root. It checks the original compressed and index hashes, all 64 window hashes and the original whole decoded member hash. Independent readback then reconstructs all windows from the sidecar and reproduces that original whole decoded hash. The named analysis also checks it on every run. The mixed analysis checks each delivered prefix against the committed prefix bytes and each of its eight full windows against the original per-window digest. It leaves 56 tails unconsumed. A same-size edit to an unconsumed tail can pass a short read and fails when that tail is read. Extent checks reject missing committed bytes at open. Other tests cover ordinal reordering, omission, swapped frame data, detached root mismatch and retaining a readonly returned value after the reader closes. [Coverage and corruption tests](../../../tests/pipeline_eval/test_seekable_member.py)

For isolated visit 37, the original reader decoded and authenticated its complete member in **125.759 CPU ms / 125.760 elapsed ms**. The sidecar loaded its metadata and verified the full visit in **3.081 / 3.081 ms**, reading **1,196,051 compressed bytes** and checking the original window hash. Its independently authenticated short prefix took **2.079 / 2.079 ms** and **717,481 compressed bytes**. Both outputs matched the corresponding original sample bytes. That sparse lookup is a different workload from a dense named pass. [Arbitrary-read clocks](measurements/seekable-member-DS30-0008.json)

### Conversion price and reach

The original data and metadata occupied **77,622,341 bytes**. The sidecar occupied **77,642,847 bytes**, a change of **+20,506 bytes** or **+0.026%** on this member, including its copied metadata and seek table. An optional copy alongside the original requires the entire additional sidecar footprint. The legacy conversion cost **251.74 CPU ms / 254.60 elapsed ms**, including **104.14 CPU ms** scoped to frame encoding and commitment hashes. Independent complete readback cost another **221.46 CPU ms / 221.47 elapsed ms**. At the smaller/larger observed mixed CPU savings, that price is recovered after 9/7 analyses, or 11/9 with the staging copy. Future capture could create the split frames from an already owned raw window, skipping source decompression and conversion. Simultaneously measuring the existing encoder, the new writer, and capture durability is still needed to price any recorder replacement. [Byte and CPU counts](measurements/seekable-member-DS30-0008.json)

The mixed route avoided **35.0%** of compressed and decoded sample bytes in this workload. For future captures stored in this seekable format, applying the observed per-member CPU savings to 106 equally behaving dense members would give an optimistic **5.7–7.4 CPU s** before additional recorder, solver, filesystem or publication effects. The earlier complete dense candidate was **12.8 CPU s** above half of its historical control. The calculation describes scale only. This future-format measurement stays outside the original DS30 2× gates, with full raw retention and reuse priced separately. [Complete dense timing budget](dense-full-short-raw.md)

### Reproduce

The first sealed 64-window DS30-0008 member came from the exact previously staged XFS copy identified by request SHA-256 `efb7e7eb718d790330d971bb6a7e704057e3b8de062394bda0b88bb12cc997c0`. The guarded transfer required **18,952/18,952** resident pages across manifest, index and payload, rechecked each held descriptor, and used `RWF_NOWAIT` without a blocking fallback. It charged **zero** filesystem input blocks and cost **100.15 CPU ms** to authenticate and place the three files in tmpfs. One first mixed control charged 256 blocks and creation charged 496 in their process-wide counters. All other measured read stages charged zero. The warm tmpfs payload path supplies no estimate of bulk storage waits. [Staging receipt](measurements/seekable-member-DS30-0008-staging.json)

The measurement used runner `230201ed` with the pinned named v3 receiver and 12 ms research receiver, CPU 2, nice 15, best-effort I/O priority 7, and a single numerical thread. The authenticated sidecar root is `sha256:cc5112e0ac9ec7be65030750803c0efd148927bd9effb149d529a202faa125f8`. Results and staging receipt SHA-256 are `b1f310a05ade750be8e6dbf09f455baa27b71cb7dcd03334130a285a852d6cd6` and `e7f73261eee60c3f6277a820a7be0c3338e55daaae8b84843c21707831e44fb4`. Thirty-nine component and adjacent tests passed. [Runner](seekable_member_trial.py)

```sh
repo=/dev/shm/leo-v3-seekable-member
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
output=/dev/shm/leo-seekable-member-0008-replay

flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$repo:$release/src:$release:$payload" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 35s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.seekable_member_trial "$output" "$short"
```
