# Wide Huffman tables miss the dense acquisition gate

On the first original DS30-0008 member, wide lookahead saved at most **0.646 ms CPU** versus upstream BMI2 X2 after charging table construction. The frozen gate was **9.45 ms per member**. The 14-bit kernel alone cut traversal from **47.646 to 36.435 ms**, but its tables took **13.850 ms** to build. On the first original DS30-0016 member, the 14-bit path saved **6.625 ms** including table construction. The best earlier builder saved 7.46 ms on that weak member. The experiment stopped before full decoder or DSP integration. [Frozen protocol](zstd-wide-huffman-protocol.md) · [Dense clocks](measurements/zstd-wide-huffman-0008-kernels.json.gz) · [Weak clocks](measurements/zstd-wide-huffman-0016-kernels.json.gz)

## Which original blocks qualify

Both already resident members delivered 64 signed windows and 102.4 MB of decoded CI16. Each used one standard frame with checksum, no dictionary or content-size field, and 782 compressed four-stream Huffman literal sections. The installed reader verified the original manifest, index, compressed bytes, every window SHA-256, complete decoded member SHA-256 and checksum on the original copy. All 19,224 weak and 18,952 dense manifest, index and payload pages were resident at admission. No new backing storage or re-encoding supplied these tests. [Weak structure](measurements/zstd-wide-huffman-0016-scope.json.gz) · [Dense structure](measurements/zstd-wide-huffman-0008-scope.json.gz)

| Original case | New / reused Huffman tables | Distinct table headers | Median / longest reuse run | Zero / nonzero sequence blocks | LZ sequences and match bytes |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 304 / 478 | 229 | 1 / 45 | 782 / 0 | 0 / 0 |
| DS30-0008 | 495 / 287 | 441 | 1 / 13 | 781 / 1 | 1 / 4 |

The candidate targets only Huffman literals. The full dense member has **102,399,996 Huffman literal bytes**, including 131,068 in its one mixed block. An exact Huffman hook ahead of the existing sequence engine could cover all of them. An independent zero-sequence block path could cover **102,268,928 decoded bytes** and needs authoritative upstream match execution and history for the remaining block. That block introduces its own Huffman table. The test does not replace sequence decoding or assume that other members are literal-only.

There are at most 548 weak and 360 dense blocks available as paired reads within their original adjacent Huffman reuse runs. That count describes the possible scope for cross-block interleaving while retaining one active shared table per run. No cross-block instruction throughput is credited. The installed decoder used 70.277 ms weak and 67.680 ms dense for the complete read calls. The exact symbol sampler found 972/1,151 weak and 900/1,081 dense samples in the stock four-stream X2 fast C loop, approximately **59.35 and 56.35 ms** after weighting by median read cost. Timer overruns make the shares approximate. [Sampler and read boundary](zstd_wide_huffman.py)

## Paid width and table cost

The new kernel derives the original canonical codes from the released weight parser and builds wider prefix tables with up to three exact bytes per entry. Four independent bit cursors consume the original reverse streams. The last bytes use an exact single-symbol table and require complete bit consumption. Adjacent identical wide entries share prefix-range construction. It uses the actual compressed Huffman sections and matches the primitive's output byte for byte over both members, including the dense mixed block's literals. Upstream X2 comes from the same pinned system static library and uses its BMI2 assembly dispatch on Gauss. Code and flags are bound in the receipts. [Native kernel](zstd_wide_huffman.c) · [Timed driver](zstd_wide_huffman_trial.py) · [Upstream 1.5.7 decoder dispatch](https://github.com/facebook/zstd/blob/v1.5.7/lib/decompress/huf_decompress.c)

| Original case and layout | Median literal CPU including tables | Median traversal CPU | Median table build CPU |
|---|---:|---:|---:|
| DS30-0016 upstream X2 | 51.041 ms | 50.338 ms | 0.552 ms |
| DS30-0016 wide 12 bit | 47.194 ms | 43.851 ms | 3.193 ms |
| DS30-0016 wide 14 bit | 44.415 ms | 36.699 ms | 7.558 ms |
| DS30-0016 wide 16 bit | 76.776 ms | 48.309 ms | 28.310 ms |
| DS30-0008 upstream X2 | 48.803 ms | 47.646 ms | 0.963 ms |
| DS30-0008 wide 12 bit | 48.157 ms | 43.224 ms | 4.758 ms |
| DS30-0008 wide 14 bit | 50.470 ms | 36.435 ms | 13.850 ms |
| DS30-0008 wide 16 bit | 90.437 ms | 47.682 ms | 42.552 ms |

The clock includes new-table parsing and construction but excludes process setup, frame read, checksum, ordinary sequences and DSP. Each layout ran four times in two opposite orders and had its complete result verified after every clock. Tables occupy 16, 64 and 256 KiB versus CPU2's 48 KiB L1 data cache. Width 14 leaves **2.917 ms** for all dense table and extra work even if its measured traversal holds. Its actual table build clock would need to fall by roughly **79%** before any integration overhead. Only 54 of 495 dense table announcements repeat an identical encoded header. Reusing those builds at their equal-cost average projects about 1.51 ms at zero cache cost. Giving away all dense 12-bit table cost still yields just **5.579 ms** versus the already available native baseline. The 0.646 ms measured arithmetic transfer is approximately **0.068 CPU s** across the historical 6,772 dense visits. This is a component projection. It does not change the through-exit evidence or the earlier upstream assembly results. [Earlier upstream assembly trial](zstd-assembly.md)

The wide decoder rejected four deliberately altered literal sections per member. The direct upstream primitive accepted two of those low-level variants and emitted different bytes. The qualification boundary is stricter than either primitive alone. Frame checksum and signed compressed and decoded SHA checks remain authoritative. Any future integration would preserve those checks and use ordinary decoding for unsupported layouts or a declined candidate. No exact full-frame fallback, malformed-input parity of an integrated path or verified receiver speedup was established here.

## Reproduction

Use the installed release interpreter and one numerical thread under the shared `gauss.lock`, CPU2, nice 15 and best-effort I/O priority 7. DS30-0016 uses its staged capture owner. DS30-0008 uses its existing tmpfs fixture owner. Each input is checked for complete file extents, residency, identity and digest before a decoder measurement. Invoke `python -Bm reports.ALGO08.v3.zstd_wide_huffman NEW_TMPFS_ROOT --case DS30-0016` for scope and `python -Bm reports.ALGO08.v3.zstd_wide_huffman_trial NEW_TMPFS_ROOT --case DS30-0016` for kernels. Substitute `DS30-0008` for the dense fixture. Twelve focused and adjacent tests passed. [Tests](../../../tests/pipeline_eval/test_zstd_wide_huffman.py)
