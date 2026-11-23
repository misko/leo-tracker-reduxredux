# Exact input verification covers every stored receiver sample

The original Zstandard members offer no way to skip decoding the unused receiver samples and still perform the installed ALGO08v3 decoded SHA-256 checks. The shorter receiver leaves **3.798 GB** of dense DS30-0008 I/Q and **548.8 MB** of lower-support DS30-0016 I/Q outside its native apertures. Those bytes remain in the current input contract. All **106** dense and **13** weaker-recording members contain at least one admitted stereo visit, so the normal all-times schedule has zero completely unpaid members. This audit used only existing metadata, receipts and saved detector output. [Dense raw pair](dense-full-short-raw.md) · [Weaker raw pair](full-short-physical.md)

## Member layout and what the hashes establish

The released recorder opens one Zstandard stream writer per member with the content checksum enabled and no advertised uncompressed size. It appends consecutive stereo windows as CI16 ordered by sample, antenna and I/Q. The published index gives decoded offsets and lengths. It has no compressed offsets for windows, antenna streams, or short-aperture tails. The measured first three original dense members were each one standard frame spanning a complete member. The native verification receipt measured 512 KiB history, 128 KiB maximum block size, a six-byte frame header and a content checksum on both measured tail members. Ordinary compressed blocks can depend on earlier decoder history or entropy tables. [Released writer](../../../src/leo/storage/writer.py) · [Released reader geometry and hashes](../../../src/leo/storage/short_window.py) · [Frame and integrity evidence](native-verified-drain.md)

The compressed SHA-256 and index SHA-256 authenticate their respective byte strings. The reader also checks each SHA-256 of decoded window bytes and the independent SHA-256 of the concatenated decoded member. Existing tests show two authenticated but inconsistent inputs, one with a wrong window digest and one with only the full decoded digest wrong. Neither takes a hash collision. Short seek intervals or separately compressed antennas could change access granularity while the existing full decoded hash still covers the whole decoded stream. The frame's 32-bit content checksum cannot substitute for either decoded SHA-256. Finalized window digests include their own padding and do not provide the chaining state for the whole decoded member. This is a statement about the coverage of the existing validation, with no claim about a lower bound on all possible SHA-256 implementations. [Independent rejection fixtures](../../../tests/pipeline_eval/test_native_verified_drain.py)

## Metadata-only coverage census

The recording bindings authenticate each read-only manifest. Totals sum its compressed, index and decoded byte counts across all consecutive chunks. For each chunk, the signed exclusion visits from the respective complete candidate packet were intersected with the global visit range obtained by adding the segment start to the chunk's first sequence. The resulting exclusions account for all issued visits.

| Recording | Issued / admitted visits | Segments / members | Compressed payload bytes | Index / manifest bytes | Decoded I/Q bytes | Bytes outside native aperture | Wholly excluded members |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0008 | 6,772 / 6,765 | 14 / 106 | 8,182,000,357 | 18,300,670 / 92,328 | 10,835,200,000 | 3,798,080,000 | 0 |
| DS30-0016 | 808 / 713 | 2 / 13 | 991,734,597 | 2,186,848 / 12,236 | 1,292,800,000 | 548,800,000 | 0 |

Dense exclusions touched seven members with one exclusion each. The weaker recording's 95 exclusions touched all 13 members, with at most 11 in any one. Bytes outside the aperture subtract `4 × (200,000 × full native lane calls + 120,000 × short native lane calls)` from each decoded total. The nominated weak DS26 comparison has 18 archived stereo clips from five recordings, with individual I/Q checks and no complete raw or cold-storage clocks. The smaller complete DS30-0016 recording provides the weaker timing comparison here. [Weak DS26 clip scope](short-signed.md) · [Dense RF block storage census](measurements/rf-block-storage.json)

## Necessary throughput with the measured publication held fixed

The acquisition allowance is half of the stock process clock minus the candidate's measured time outside acquisition. Subtracting its native receiver span gives the budget for all other acquisition. The resulting MB/s values are necessary effective rates for complete logical byte coverage, using decimal MB. The compressed rates omit the separately priced index and manifest bytes. The after-native elapsed rates budget serial verification time. Input prefetch can overlap storage service, and cache residency can reduce physical disk traffic.

| Quantity | Dense DS30-0008 | Weaker DS30-0016 |
|---|---:|---:|
| Stock target at half process elapsed | 74.943 s | 7.261 s |
| Remaining total acquisition elapsed | 39.963 s | 1.214 s |
| Compressed / decoded effective MB/s needed in that span | 204.7 / 271.1 | 816.6 / 1,064.5 |
| Remaining acquisition elapsed after unchanged native calls | 22.371 s | −0.462 s |
| Compressed / decoded effective MB/s needed after native calls | 365.7 / 484.3 | — |
| Remaining total acquisition CPU | 19.603 s | −0.343 s |
| Remaining CPU after unchanged native calls | 2.252 s | −2.019 s |
| Compressed / decoded effective MB per CPU second after native calls | 3,632.8 / 4,810.8 | — |

Stock began with 76.75% resident payload pages on dense and zero on the smaller recording. The respective candidates had 2.84% and 100% resident. The observed complete-pair clocks therefore remain cache-sensitive. The smaller case's measured CPU outside acquisition already exceeds half stock CPU. Its existing native detector alone exceeds the entire elapsed acquisition allowance. This excludes an input-only path to 2× for that case with the rest fixed, even granting free reads and verification. [Dense clock receipt](measurements/dense-full-short-raw.json.gz) · [Weaker clock receipt](measurements/full-short-DS30-0016-raw.json.gz)

The existing exact native drain achieved **503–574 compressed MB/s elapsed** and **622–627 compressed MB per CPU second** over two wholly unpaid dense members. It used one reusable decoded buffer, checked both decoded hash levels, and emitted original empty-row metadata. Repeating those elapsed and CPU rates by visit count would charge **14.24–16.26 s elapsed / 13.06–13.14 CPU s** on dense and **1.70–1.94 s / 1.56–1.57 s** on the smaller case, even with no native receiver work. These are transfers from two skipped members, with only the private file-page state controlled. The rates leave dense elapsed physically open at that local rate and miss the dense post-receiver CPU budget by a wide margin. Sparse full acquisition reached **263–303 compressed MB/s elapsed** on three private dense members while paying native detection on one member. Direct I/O bypassed file pages but did not show repeatable elapsed savings. [Unpaid native drain receipt](measurements/native-verified-drain.json) · [Sparse verified acquisition](sparse-cold-input.md) · [Direct-I/O reversal](dense-direct-cold.md)

The RF-block policy still touched all 106 dense members among its unpaid visits and failed the containing-position screen. Early geographic rejection can avoid later inference on a decisive exterior offer after signed waveform acquisition. It supplies no proof to omit the original input bytes. A prior verified snapshot can serve a saved-input solve; making such a snapshot stand in for fresh raw verification would require a separately trusted validation record bound to the exact input and decoder. The existing raw contract has no such handoff. [RF block tradeoff](rf-block.md) · [Early-region outcomes](early-region.md)

The metadata census pins DS30-0008 binding SHA-256 `a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a` and candidate packet `ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85`. DS30-0016 uses binding SHA-256 `c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c` and candidate packet `c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589`. The linked raw receipts retain the individual manifest pins and process and acquisition clocks. No compressed member was opened for this audit.
