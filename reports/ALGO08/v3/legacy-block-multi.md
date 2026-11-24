# Three exact exceptions on one original physical member

The multiple-exception reader verified all **64 original full visits and 64 prefixes** of DS30-0016 global member 3. It recovered three sequence-bearing blocks through complete, consecutive libzstd decoding with decoded history intact. Each selective output matched the installed reader at every CI16 word. The 427,753-byte detached map carries 393,216 bytes of exact exception material and 34,537 bytes of metadata. It adds 0.546% to the original 78,317,175 compressed bytes. The manifest, original index, complete encoded member, raw input and capture identities did not change. [Frozen protocol](legacy-block-multi-protocol.md) · [Measured receipt](measurements/legacy-block-multi-0016.json.gz)

| Exceptional block ordinal | Actual decoded start (bytes) | Actual decoded count (bytes) | Earlier Huffman owner |
|---:|---:|---:|---:|
| 120 | 15,728,640 | 131,072 | 113 |
| 135 | 17,694,720 | 131,072 | 135 |
| 676 | 88,604,672 | 131,072 | 674 |

Libzstd’s `ZSTD_nextSrcSizeToDecompress` and `ZSTD_nextInputType` supplied the exact expected input size and classified each header, payload and checksum. The decoder's per-block result supplied each actual output extent. It retained contiguous earlier output to resolve genuine LZ matches. Before sealing a sidecar, the driver checked the entire decoded SHA and independently exhausted the released stock reader. It compared actual bytes against all 64 exact stock windows. A synthetic frame with prior-block matches independently exercises three distinct submaximum decoded sizes of 40,000, 57,192 and 86,016 bytes, including a single request that spans all three exceptions. The checksum mutation in that test fails at the native complete-frame boundary. [Source](legacy_block_multi.py) · [Tests](../../../tests/pipeline_eval/test_legacy_block_multi.py)

The prefix checks consumed 166,400 exact bytes across two exception spans and returned 40,960,000 bytes. They decoded 372 original ordinary blocks plus 15 ordinary table-owner replays. Those replays added 1,503,023 encoded and 1,966,080 decoded bytes. The separate all-full check used all three exact exception ranges and decoded each of 779 original ordinary blocks with no table-owner replays. None of the three exceptions on this member owns a table used by a later ordinary block. The adapter configures the reviewed native exception-owner port when one such dependency exists and the supplied library supports it. More than one exceptional table owner, unsupported frame types and more than 16 exceptions are declined before issuance. Copied exception ranges never enter native sequence decoding during use. Integrity failure closes the active reader and propagates without a same-state stock fallback. [Common API](legacy_block_multi.py)

| Measured resident operation | Elapsed / CPU (ms) |
|---|---:|
| Complete released stock verification | 208.088 / 208.065 |
| Independent native history decode, exact comparison and map seal | 235.881 / 235.778 |
| Detached write and sync | 0.172 / 0.172 |
| Selective prefix attach, including complete original authentication | 56.066 / 56.065 |
| Selective prefix decode, digest and exact word comparison | 39.944 / 39.904 |
| Selective full attach, including complete original authentication | 114.973 / 114.971 |
| Selective full decode, digest and exact word comparison | 86.367 / 86.362 |

The attachment clocks include different metadata demands. Full attachment recorded 60.577 ms of metadata versus 1.010 ms during prefix attachment. These diagnostic cases carry different request workloads, with independent exact verification included in both. They give no ready raw-to-exit or steady-state production ratio. Source pages were already fully resident and all measured publication scopes record zero input blocks. The experiment read one original member in tmpfs and performed no detector or solver calls. [Detailed clocks](measurements/legacy-block-multi-0016.json.gz)

The as-run freeze is `d62a23d81`. The uncompressed receipt SHA-256 is `c8a7fd98b37e04c40955845dfffa08f715a1c134255b3a99b7fb94d20c66e253`. The private output is `/dev/shm/leo-v3-legacy-block-multi-result01`. The report archives digests and measurements only. Ten component and adjacent tests passed. [Runner](legacy_block_multi_trial.py)
