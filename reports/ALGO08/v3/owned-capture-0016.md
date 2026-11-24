# Writing and independently reading back all saved DS30-0016 visits

From already owned CI16 words, the conventional writer took **1.919 s elapsed** and direct private packed output took **1.191 s** across the two saved physical segments. Independent complete readback brought the totals to **3.583 s** and **2.549 s**, respectively. The private route saved **1.033 s** at that boundary. The installed reader accepted the conventional archive and stopped at manifest discovery on the private root. [Full measurement and custody receipt](measurements/owned-capture-DS30-0016.json.gz)

| Boundary | Ordinary CPU / elapsed (s) | Direct packed CPU / elapsed (s) |
| --- | ---: | ---: |
| First segment, 512 visits | 1.219191 / 1.219507 | 0.750105 / 0.750138 |
| Final segment, 296 visits | 0.699133 / 0.699158 | 0.440401 / 0.440424 |
| Both writes and recording envelope | 1.918470 / 1.918810 | 1.190560 / 1.190615 |
| Independent complete readback | 1.663694 / 1.663968 | 1.358590 / 1.358814 |
| Write and complete readback | **3.582165 / 3.582779** | **2.549150 / 2.549429** |
| Retained archive bytes, including envelope | **993,941,093 B** | **968,794,236 B** |

The offline job processed the full staged inventory of **808** visits, **13** members and **1,292,800,000 decoded bytes**. It gave both writers the same immutable arrays for each segment. Order reversed across segments, with the ordinary writer first on the longer segment. Freshly written archives were retained together, with an accounted maximum of **2,515,116,235 B** including the owned sample buffers and one extra compressed member. The separate hydration cost was **2.105 CPU s / 2.105 elapsed s**. It authenticated the original tmpfs recording and charged zero input blocks. Complete readback in both arms also charged zero. The first ordinary write recorded one process major fault and 16 input blocks while receiving only owned arrays. Two earlier environment checks stopped at imports before opening samples. [Source bounds and machine clocks](measurements/owned-capture-DS30-0016.json.gz)

The timed writer scopes include both archive writers' file flushes and `fsync`, segment rename and directory `fsync`, plus an externally pinned recording envelope that binds segment order, roots and lifecycle. The 296-visit final segment retained its original `incomplete` state and fault. Independent readback reopened each root. The ordinary writer reproduced all 13 original compressed seals, and both paths reproduced every original index, window hash and whole decoded member digest. The packed reader authenticated **1,616 encoded blocks** and its exact encoded and decoded block commitments matched every member of the previously timed strict Cairo derivative. Both layouts had their own fresh capture identities. The tmpfs sync boundary exercises the complete publication sequence. Power-loss durability and device flush costs remain unmeasured. [Original and packed writer implementations](../../../src/leo/storage/short_window.py) · [Private packed writer](direct_packed_capture.py) · [Commitment comparisons](measurements/owned-capture-DS30-0016.json.gz)

### Compatibility and amortization

The released `FastScanStore.inventory` discovers the `manifest.json` files in a recording or its segment directories. The private segment roots use `capture.json`, so the released inventory returned `no sealed fast-scan segments` before accessing packed payload. The current strict derivative input also starts with a normal `FastSegmentSource` and checks each derivative against the exact ordinary manifest and chunk. A private recording source would have to be integrated before the direct packed archive could replace the ordinary archive. [Released inventory](../../../src/leo/storage/fast_scan.py) · [Strict derivative admission](packed_combined_input.py)

Keeping both archives preserves the ordinary reader's input. In this serial fanout, the incremental private write was **1.191 s** and added **968.8 MB**. Including separate complete private readback makes the extra cost **2.549 s**. The previous same-receiver resident Cairo comparison took **7.677 s** with ordinary input and **6.542 s** with its prepared strict derivative, a difference of **1.135 s**. If a consumer can achieve that saving from the direct output, the measured private write breaks even after **2** analyses, or **3** when charging independent complete private readback. The existing converted derivative cost **4.985 s** before prepared analysis, implying **5** analogous analyses. These arithmetic comparisons use one earlier analysis pair. This writer trial ends at readback, before DSP, solving or publication. [Strict and original-input Cairo timings](strict-cairo-0016.md)

### Public-schema Zstandard alternative

The installed Zstandard stream reader can read a normal `.zst` containing one frame per nonempty visit in chronological order. A synthetic test exercised the installed reader and python-zstandard **0.25.0** with mixed zero, shortened and full visits and an all-zero member. The original index stays intact. A zero visit has no corresponding stored frame, and an all-zero member has one valid empty frame to meet the positive encoded-size constraint. Before terminating each nonempty frame the test flushed a Zstandard block at the lesser of the signed sample count and 80,000 samples. An optional externally pinned seek table bound the fresh manifest, original index, full compressed seal, frame offsets and prefix hash. After authenticating the whole compressed member, a seek reader decoded each prefix from just the flushed fragment and recovered each whole visit independently from its complete frame. The released reader reconstructed the exact chronological full window bytes with the unchanged schema. [Compatibility fixture](../../../tests/pipeline_eval/test_owned_capture_0016.py)

Two independently encoded frames inside one visit follow a different boundary. The installed `stream_reader` stops a read at a frame boundary. The conventional reader then rejects the short decoded window. Explicit `read_across_frames=True` recovers the stream, and would require a change to the installed reader. Existing concatenated-frame tests already demonstrate whole-visit frames with released fallback. The block-flush fixture extends them to prefixes within a single frame. Full compressed authentication still charges every encoded byte even when a seek consumer avoids decoding tails. Any new encoding must publish its own compressed digest and size. The historical manifest still authenticates its original encoding, while index, per-window and decoded-member hashes can stay the same under re-encoding. The synthetic compatibility check supplies no physical encoder clocks or compression ratio. [Prior concatenated-frame tests](../../../tests/pipeline_eval/test_native_verified_drain.py) · [Released reader](../../../src/leo/storage/short_window.py)

### Reproduce

The physical runner is pinned at `bdd94b01`. The uncompressed receipt SHA-256 is `ff29cfe59f81f6ebfb97c5238647d2707e7a66f9e998e07314afb29f279d917a`. The physical job ran once on CPU 2, nice 15, best-effort I/O priority 7, one numerical thread, with the normal read-only recording account and the shared Gauss lock. Thirty-nine focused and adjacent tests passed. The frame-boundary fixtures also passed directly under the installed reader. [Runner](owned_capture_0016.py)

```sh
repo=/dev/shm/leo-v3-owned-0016-writer
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=/dev/shm/leo-v3-owned-0016-writer-replay

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -x -w 150 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env PYTHONPATH="$repo:$repo/reports/ALGO08/v3:$release/src:$release:$payload" \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/timeout 55s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.owned_capture_0016 "$out"
```
