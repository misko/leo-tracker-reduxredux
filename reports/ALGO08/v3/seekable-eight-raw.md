# Complete encoded verification with a true 8 ms native read

The private 8/12 ms split archive fed the actual signed all-visit 20/8 ms receiver on two previously staged physical members. Complete encoded verification read every committed packed block and decoded only the real native aperture. It reproduced the entire ordinary 20/8 ms native document and the original EOF selection byte for byte on both members. Whole-member acquisition took **207.045 CPU ms on dense DS30-0008** and **192.869–202.504 ms on held DS30-0169**, before the EOF clock. The identical ordinary 20/8 ms path took 348.802 ms in the clean dense comparison and 338.372–361.166 ms on held. Legacy conversion and independent full readback cost 492.341 and 430.068 CPU ms, respectively. One-time conversion outweighed every first archival use saving.

| Scope | Dense CPU / wall ms | Held CPU / wall ms |
| --- | ---: | ---: |
| Named installed 20 ms acquisition | 488.267 / 488.298 | 432.935 / 434.703 and 447.510 / 447.742 |
| Ordinary original-member 20/8 | 348.802 / 349.062 | 361.166 / 362.080 and 338.372 / 338.378 |
| Complete encoded verification | 207.045 / 207.054 | 202.504 / 203.554 and 192.869 / 193.414 |
| Demand-only verification | 169.992–172.568 / 169.996–172.571 | 154.591 / 155.751 and 153.100 / 153.361 |
| Legacy conversion | 328.335 / 328.348 | 252.913 / 253.818 |
| Independent complete readback | 164.006 / 164.010 | 177.156 / 178.011 |

The dense named and strict clocks use the same pinned scanner, per-member boundaries, production buffer and one-member prefetch context, paired hardware SHA, index validator, residency and numerical host settings. No next-member request was issued. The dense demand clocks come from the preceding reversed-order conversion trial. Held named clocks come from two earlier paid original scanner runs, verified against the same complete compressed and index digests, all 64 original ordered window hashes, identical cutoff, clocks, exclusions and signed opportunity fields. Those earlier runs reported zero lookahead attempts. The dense fixture enrolled 64/64 visits and held enrolled 51/64. Each 20/8 arm preserved the original eight two-scan anchor visits plus 56/43 short visits on both radios. It returned 70/56 factors over 128/102 probe rows, with EOF choosing unfiltered in every case. Named 20 ms returned 19/15 factors over the same opportunities. The detector changes account for that difference. The storage change within 20/8 kept the actual signed factor values and outcomes exactly. [Frozen protocol](seekable-eight-raw-protocol.md) · [Machine receipts](measurements/seekable-eight-raw.json.gz)

## Storage and integrity

| Physical member and read mode | Compressed or packed payload bytes | Decoded stereo bytes |
| --- | ---: | ---: |
| Dense, original | 77,442,779 | 102,400,000 |
| Dense, complete encoded | 76,440,256 | 48,640,000 |
| Dense, demand | 36,360,144 | 48,640,000 |
| Held, original | 78,852,856 | 102,400,000 |
| Held, complete encoded | 76,800,256 | 40,320,000 |
| Held, demand | 30,240,118 | 40,320,000 |

These are logical payload extents exclusive of metadata. The packed archive with original metadata and independent seek table occupies 76,642,953 and 77,003,662 bytes. Strict verification's encoded I/O saving is the change in total encoded size. It decodes 52.5%/60.6% fewer stereo bytes. Demand omits 41.083/48.613 MB of original encoded extent before filesystem effects. All original waveform data was already resident in tmpfs. Comparisons recorded zero process input blocks and major faults. Neither representation has been timed against cold backing storage.

The detached expected root is independent of the derivative. Conversion checks the original signed metadata, compressed and each decoded window hash, and whole decoded member digest. Complete readback confirms the derivative reconstructs the same member. Every strict acquisition subsequently authenticates all current encoded bytes under that root. The exact pinned codec and independent readback bind the original decoded equivalence, and every requested decoded block plus every full anchor is checked again. Ordinary DS30 retains its own complete per-run checks.

On each real member, corrupting one byte in the unused tail of visit eight made strict acquisition fail before reading the first native opportunity. Demand safely checked its requested ranges and reproduced the same factors. An explicit read of the corrupt tail failed with the same digest mismatch. Demand thus cannot provide the existing whole-member live assurance for bytes it never reads. The study restored both private derivatives after testing. The full reader still rejects short, missing or reordered committed files. [Seekable storage boundary](seekable-member.md) · [Original installed full-hash constraint](packed-combined-demand.md)

## Timing interpretation

The first dense run's independent ordinary clocks were 445.187 and 564.702 ms CPU, much higher than the archived same-member mixed clocks of 272.496 and 287.792 ms. The clean direct pair isolated 202.601 ms CPU in the original verified iterator, including 102.594 ms in compressed-member retrieval plus digest. The new named verified iterator took 133.325 ms including 32.146 ms for that same descriptor and digest. The roughly 70 ms descriptor difference explains the entire iterator gap. The actual whole trials kept that time. A diagnostic that substitutes the faster descriptor time alone gives 278.354 ms for ordinary 20/8 and a 71.309 ms representation saving against the new strict clock. It agrees with the scale of the earlier warm control and supplies no normalized clock as a measurement. On held, the actual reversed strict representation deltas were 158.662 and 145.502 ms CPU.

Dense strict checked the 128 encoded blocks in 45.416 ms CPU. Held took 42.662–52.543 ms. Separately clocked model validation took 0.570/1.027 ms on the clean dense pair and 0.542–0.656 ms on held. The final native binding took 0.270/0.299 ms on dense. The dense EOF cost normally sat around 3.7 ms after imports, with 13.0 ms on the first clean control. The setup, codec compilation, input admission and EOF phases are recorded separately. Equal placement in the same physical harness does not eliminate variation in copied and hashed pages.

Using stable dense historical ordinary clocks only for scale, the strict representation advantage is about 65–81 ms per member. Multiplying by 106 would give 6.9–8.6 s before geographic solve, filesystem scheduling or archive generation. It is an illustration rather than a dense measurement. The dense legacy conversion cost amortizes around the fourth analysis using the clean observed 141.756 ms saving, or seventh to eighth using the historical-scaled interval. With held's observed deltas, the model crosses on the third analysis. An initial strict use from already archived ordinary data costs about 699 CPU ms dense and 623–633 ms held before EOF and one-time library setup. It is slower than starting on either existing ordinary detector. The strict stage is promising for repeated analysis or future recorder-native storage, where the initial original decode can be avoided. A recorder write and durability trial is needed for first-use performance.

Three startup checks failed before waveform traversal. A package import supplied a relative module outside its namespace, then the lean runtime observed an already imported storage facade. A final dependency check found a historical benchmark helper missing from the pinned payload. Direct pinned imports and the correct startup order resolved those issues. The initial affected root contained a compiled codec only. No measured observation or receiver output was repeated to recover from these startup errors. The later clean dense pair was a prespecified attribution check using the original already verified derivative. Each physical scope remained one member, with no collection, deployment or ordinary input contract edits.

Twenty-seven focused and adjacent tests cover both prior and current layouts and the raw adapter. [Adapter and trial](seekable_eight_raw.py)
