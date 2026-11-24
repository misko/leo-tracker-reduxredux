# Verified one-pass staging of original Zstandard input

Decoding original Zstandard input into a single immutable slab preserved **every ordered signed output byte** on the first original resident members of DS30-0008 and DS30-0169. Verified acquisition CPU saved **16.1–19.5%** on DS30-0169, which paid an unusually expensive whole-file descriptor read. On dense DS30-0008 it added **2.65%** in one order and saved **0.50%** in reverse. The combination failed the 5% floor across both members. Both files used the same ordinary tmpfs file and descriptor type, which gives no defensible type-based selector for the faster path. [Frozen protocol](sealed-stream-protocol.md) · [Dense acquisition receipt](measurements/sealed-stream-0008.json.gz) · [Independent acquisition receipt](measurements/sealed-stream-0169.json.gz)

| Case and order | Verified acquisition CPU, original → slab (ms) | Verified acquisition wall, original → slab (ms) | Process CPU, original → slab (s) | Process wall, original → slab (s) |
| --- | ---: | ---: | ---: | ---: |
| DS30-0008, original first | 323.139 → 331.716 | 323.147 → 331.731 | 1.324 → 1.356 | 1.326 → 1.357 |
| DS30-0008, slab first | 330.240 → 328.587 | 330.248 → 328.595 | 1.351 → 1.381 | 1.352 → 1.382 |
| DS30-0169, original first | 397.950 → 320.309 | 398.865 → 321.308 | 1.451 → 1.362 | 1.455 → 1.375 |
| DS30-0169, slab first | 375.443 → 314.974 | 375.474 → 316.630 | 1.370 → 1.328 | 1.373 → 1.341 |

Each fresh process authenticated the same 64 original visits under the same pinned lightweight receiver binding and low-priority CPU2 lock. DS30-0008 emitted the original 128 ordered probes, including empties, with 70 signed selections. DS30-0169 emitted 102 original probes and 56 selections after applying the original 13 exclusions. Both arms verified 102,400,000 decoded bytes per member and paid all 16 original two-scan anchor lanes. Candidate fallbacks were zero. The native receiver used its shipped binaries in every run. [Complete signed packets and clocks](measurements/sealed-stream-0169.json.gz)

## Mandatory ingress in the measured budget

The native port reads one ordinary descriptor in 256 KiB blocks, applies the original compressed SHA-256 to the same bytes it sends into pinned system Zstandard 1.5.7, and writes into the final declared decoded slab. Zstandard's stable output mode keeps its history in that allocation and handles the original frame checksum. Paired SHA-NI checks each original indexed window and the complete decoded member. The loader verifies unchanged descriptor identity, exact EOF, frame completion and all digests before any decoded window reaches DSP. The installed signed index parser and window data checks remain in the path. Unsupported layouts take the stock reader. [Native transaction](sealed_stream.c) · [Reader binding](sealed_stream.py) · [Native build](measurements/sealed-stream-build.json.gz)

| Case and operation | Original CPU across two runs (ms) | Slab CPU across two runs (ms) |
| --- | ---: | ---: |
| DS30-0008 descriptor read | 15.027–15.361 | 8.416–8.875 |
| DS30-0008 compressed SHA-256 | 16.953–17.112 | 15.366–15.426 |
| DS30-0008 Zstandard | 72.238–73.090 | 77.176–77.818 |
| DS30-0008 decoded SHA-256 | 23.637–23.664 | 23.662–23.700 |
| DS30-0169 descriptor read | 74.667–91.066 | 7.703–8.002 |
| DS30-0169 compressed SHA-256 | 17.060–17.217 | 15.606–15.741 |
| DS30-0169 Zstandard | 76.227–77.077 | 83.829–87.013 |
| DS30-0169 decoded SHA-256 | 23.599–23.658 | 23.592–23.746 |

The lowest measured slab costs for read, decode and hash together were **124.62 ms** on DS30-0008 and **131.02 ms** on DS30-0169, before context, index validation, scheduled DSP or sealing. The archive requires decoding and the independent compressed, per-window and whole-decoded digests. Zstandard was the largest recurring ingress component after bounding the descriptor read. The slab kept a single 102.4 MB immutable decoded allocation plus bounded compressed scratch, replacing the 77.4 or 78.9 MB complete compressed allocation and normal per-window staging. It completes all those checks before first DSP. Previous full-frame arenas kept a second complete encoded input, while provisional incremental stages ran DSP before the compressed seal. [Previous decoded arena](fused-block-input.md) · [Prior independent decoder gain](dense-zstd-backend.md) · [Provisional incremental boundary](incremental-ingress.md)

## Isolated descriptor and SHA control

The exact bound files were `/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000/iq-000000.ci16.zst` and `/dev/shm/leo-receiver-ceiling-0169-results01/fast8-auto-20261116-022353-b914c97a-1-lower-segment-00000000/iq-000000.ci16.zst`. Both were direct single-link regular files on the same tmpfs mount, ID 42 and device 27, with inodes 636225 and 739926. The signed payloads were 77,442,779 and 78,852,856 bytes. They were read by their staged paths, with no bind mount or symlink alias. Both complete runs and the isolated test used the previously verified local copies. The 18,952 dense and 19,297 independent pages including index and manifest stayed resident. All complete and isolated runs recorded zero major faults and zero process input blocks.

| Case and isolated order | Released whole-read CPU (ms) | Whole read and compressed SHA CPU (ms) | Bounded read and compressed SHA CPU (ms) | Minor faults, whole / bounded |
| --- | ---: | ---: | ---: | ---: |
| DS30-0008, whole first | 69.050 | 85.911 | 23.123 | 14,308 / 21 |
| DS30-0008, bounded first | 59.024 | 75.921 | 23.176 | 12,264 / 0 |
| DS30-0169, whole first | 128.782 | 146.020 | 22.889 | 8,521 / 0 |
| DS30-0169, bounded first | 179.945 | 197.218 | 22.748 | 6,477 / 0 |

The isolated whole arm used the deployed pathname-based `read_regular` function, then hashed its returned buffer. The bounded control used a 256 KiB Python read buffer and the same digest without entering Zstandard or DSP. Both exactly verified their original compressed digest in both orders. Bounded read-plus-hash took 22.75–23.18 ms alone and 23.37–24.30 ms in the slab's native transaction. Whole-read CPU varied substantially even though all four original descriptor tests read the same two resident inodes. In the isolated check DS30-0169 was slower with fewer recorded minor faults. Those counters do not identify the causal share of allocation, page handling or copy behavior. An earlier warm same-member descriptor measured 15.39 ms median and a 3.99 ms first-touch saving with a reused destination. The two case and launch contexts therefore give a repeatable bounded-read cost and variable whole-read costs, with zero evidence of backing reads or a stable file-type discriminator. [Dense isolated receipt](measurements/sealed-stream-descriptor-0008.json.gz) · [Independent isolated receipt](measurements/sealed-stream-descriptor-0169.json.gz) · [Earlier fault controls](destination-faults.md)

## Reproduce

Use the pinned release Python, shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. Use the original dense fixture owner for DS30-0008 and `leo` for DS30-0169. Under `88d493c0b`, the dense paid run completed and the independent launch stopped on the dense default path before waveform access. The corrected active-member binding at `0ef063607` ran the independent pair only. A prior partial dense setup attempt stopped before its candidate acquisition on a context expression error. The two reported complete pairs use the same marked native DSO. The isolated descriptor method at `8541690f8` uses the frozen released pathname port. Thirty-three focused and adjacent tests passed, including immutable retention, independent digest and checksum failures, and the original-reader fallback. [Acquisition driver](sealed_stream_trial.py) · [Descriptor control](sealed_stream_descriptor.py) · [Tests](../../../tests/pipeline_eval/test_sealed_stream.py)

```bash
python -Bm reports.ALGO08.v3.sealed_stream /dev/shm/sealed-stream-build
python -Bm reports.ALGO08.v3.sealed_stream_trial launch /dev/shm/sealed-stream-dense 0008 /dev/shm/sealed-stream-build
python -Bm reports.ALGO08.v3.sealed_stream_descriptor /dev/shm/sealed-stream-descriptor-dense.json 0008
```
