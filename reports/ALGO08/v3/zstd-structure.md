# What the stock Zstandard decoder executes on a signed resident member

The admitted 64-visit public North member contains **802 compressed blocks, all with zero sequences and four Huffman streams**. The installed decoder's read CPU was **71.41–72.18 ms**. Its four-stream X2 fast C loop accounted for **78.2% of sampled decoder PCs**, and literal decode altogether accounted for **86.1%**. A raw-block zero-copy bypass would cover **zero bytes** on this member. [Frozen protocol](zstd-structure-protocol.md) · [Authenticated receipt](measurements/zstd-structure-north.json.gz)

The private copy of the first physical DS30-0008 member had **0 of 18,952** combined manifest, index and compressed payload pages resident. It was rejected before reading content. The existing public North tmpfs source had all 20,584 combined pages resident. The sampler used its first authenticated member only, preserving the released manifest, compressed and index integrity checks, all 64 window SHA-256 checks, whole decoded SHA-256 and the stock interaction with the frame checksum. The snapshot read from disk once and the repeated trials consumed the same in-memory compressed bytes. [Previous public fixture](warm-six-prefetch.md)

| Signed member structure | Measured quantity |
| --- | ---: |
| Encoded frame bytes | 84,255,971 |
| Decoded bytes | 102,400,000 |
| Raw / RLE / compressed frame blocks | 0 / 0 / 802 |
| New / reused Huffman tables | 196 / 606 |
| Huffman encoded literals, including new tables | 84,248,743 bytes |
| Regenerated Huffman literals | 102,400,000 bytes |
| Encoded sequence sections | 802 bytes |
| Match commands / regenerated match bytes | 0 / 0 |

Each sequence section was the zero-count byte. The frame includes a checksum and omits the optional content-size field. The original decoded size comes from the authenticated manifest and verified read. Raw frame blocks and raw literals are distinct structures. Both are absent here. [Format specification](https://www.rfc-editor.org/rfc/rfc8878.html#section-3.1.1.3)

## Measured decoder work

The exact installed Python C extension read 64 × 1.6 MB plus the trailing-byte check. Four unprofiled decoder-read clocks averaged **71.704 ms CPU**. The full signed reader over the held snapshot used **131.56–132.74 ms CPU** per unprofiled pass, including original metadata and SHA checks. The sixteen profiled passes averaged 71.485 ms CPU inside reads. The CPU timer attributed only interrupted PCs during those reads using exact pinned ELF text symbols. It delivered 1,130 samples and reported 1,130 timer overruns at its nominal 500 µs interval. The interruption clock and unresolved samples make the fractions approximate.

| Decoder samples | Count | Share |
| --- | ---: | ---: |
| Four-stream X2 fast C loop | 884 | 78.2% |
| Other literal decode, including X1 | 89 | 7.9% |
| Frame checksum implementation | 64 | 5.7% |
| FSE workspace decoder | 3 | 0.3% |
| Unresolved | 90 | 8.0% |
| Sequence decode / execution symbols | 0 | 0% |

The command census proves the frame carries no match execution. The generic sequence header work remains, and FSE can decode Huffman table descriptions even with no match commands. The extension's X2 fast C loop actually executed, and its disassembly includes the BMI2 `shlx` instruction. Gauss exposes BMI1, BMI2 and AVX2. The previous build inspection found the upstream four-stream BMI2 X1 and X2 assembly routines in the system 1.5.7 library, while the installed bundled extension has the fast C loops. Upstream dispatch selects the assembly fast loop when it is built and enabled and the CPU and call flags qualify. [Prior ELF build audit](dense-zstd-backend.md) · [Upstream 1.5.7 dispatch](https://github.com/facebook/zstd/blob/v1.5.7/lib/decompress/huf_decompress.c#L1587-L1615)

## Budget

A frame-level bypass has zero eligible decoded bytes. A direct literal-placement optimization would leave the actual Huffman decode and required checksum in place. Even granting the entire unresolved 8.0% for that optimization yields about **5.71 ms per measured member**, or **0.60 s** at 6,772 issued visits with this decoder profile and the same per-visit extent. The available measurements leave no way to price this as a proven dense physical saving.

One dense second needs about **9.45 ms per 64-visit member**. If the public X2 share carried to the prior 7.514 s dense decoder estimate, the X2 loop would have to become about **17% cheaper** to save that second. The concrete upstream candidate is the four-stream X2 BMI2 assembly loop. The earlier measured whole system build improvement, 9.48–10.54 ms per physical member in the matched stream bridge, is of that order. Complete acquisition showed mixed signs in those runs, and changing the entire build does not isolate the assembly contribution. A same-library selector can separate it without changing any checksum. The physical frame's literal and sequence proportions remain unmeasured. [Dense prefix attribution](dense-ingress-attribution.md) · [Earlier backend comparison](dense-zstd-backend.md)

Seven component tests passed. Use `python -BPs -m reports.ALGO08.v3.zstd_structure_trial PRIVATE_TMPFS/trial` under the installed release environment with `gauss.lock`, CPU 2, `nice -n15`, `ionice -c2 -n7` and one numerical thread. The driver applies passive admission before opening candidate content. The receipt expands to SHA-256 `4e90828fb7f194693f405eaddd0bed1789b7e36291d3babd5d0edd1087687548`. [Header parser](zstd_structure.py) · [Sampler](zstd_decoder_pc.c) · [Trial](zstd_structure_trial.py)
