# Block-floating IQ through the unchanged 20/8 receiver

On the first signed DS30-0016 member, **8-bit IQ changed the receiver's
measurements materially**. It created a short detection in a formerly
empty lane and changed the selected carrier in another by 251,058 Hz
and 5,501 pilot-period-wrapped samples. The prespecified 10-bit control
preserved every selected branch, native rank and continuation vote in
this member. Its matched selected CFO moved by **1.234 Hz RMS** and at
most **5.610 Hz**. This is one weak physical prefix and does not measure
localization, recorded transport, or a new survey. [Frozen protocol](iq-block-float-protocol.md)

| Reconstruction | Stored IQ bytes | Quantize CPU | Reconstruct CPU | 20/8 callback CPU |
| --- | ---: | ---: | ---: | ---: |
| Original CI16 | 102,400,000 decoded | — | — | 130.824 ms |
| 8-bit | 51,200,064 | 44.014 ms | 7.207 ms | 130.888 ms |
| 10-bit | 64,000,064 | 48.658 ms | 15.056 ms | 129.843 ms |

Both widths encode all 64 issued stereo visits, including the six
excluded by the original metadata. Each measured visit used shift 4
for 8 bits and shift 2 for 10 bits. The maximum CI16 error was 15 and
3 counts respectively, with clipping observed only on excluded visits.
Each packed extent counts the 64 scale bytes. The corresponding
original on disk is 78,554,951 bytes of Zstandard, so the raw encoded
payload savings are 34.8% and 18.5%. The earlier exact split packing
stored 76,799,710 bytes on this member, about 12.8 MB larger than this
10-bit payload. The derived byte counts and codec CPU exclude any
future authenticated container, transfer, hashing and writes.
[Prior lossless first-use measurement](ci16-packed-storage.md)

## Signed detector outcomes

The unmodified control reproduced every probe in the first-member
prefix of the independent full signed 20/8 packet. Each arm received
the same 116 native opportunities across eight full and 50 short
admitted stereo visits.

| Evidence | Original | 8-bit | 10-bit |
| --- | ---: | ---: | ---: |
| Empty lanes | 73 | 72 | 73 |
| Lanes with only a first native factor | 39 | 40 | 39 |
| Lanes with both first and second native factors | 4 | 4 | 4 |
| Selected first factors | 43 | 44 | 43 |
| Continued short lanes | 7 | 8 | 7 |
| Original selected branches matched | 43 | 42 | 43 |
| Signed CFO median / RMS / max abs on matched selected branches, Hz | — | −0.278 / 4.041 / 21.786 | +0.039 / 1.234 / 5.610 |
| Max absolute fractional epoch change on matched selected branches, samples | — | 0.01704 | 0.00391 |

At issued visit 29 and receiver 0, the 8-bit reconstruction changed
the rank-zero choice from −366,305.449 Hz to −115,247.331 Hz. This
branch replacement is excluded from its matched-only CFO error row.
At visit 63 and receiver 1, the new rank-zero output had zero
continuation votes. Separately, the short positive at visit 61 and
receiver 0 gained a third vote and became the eighth continued lane.
These are receiver and continuation effects on the same original
chronology. No samples or candidate labels from other recordings were
used. [Lane-level comparison and full native rows](measurements/iq-block-float-0016.json.gz)

## Boundary

The measured encode and decode kernels reconstruct whole visits in
memory. The original 78.6 MB compressed member was authenticated
and decoded once before measuring these phases, at 169.639 ms wall /
169.623 ms CPU. Its 19,224 manifest, index and payload pages were
resident and the read recorded zero input blocks. The original
recording and signed hashes remain authoritative. Encoded and
reconstructed bytes have their own distinct SHA-256 values in the
receipt. A conversion of already recorded originals would still have
to acquire and verify those originals first. The assay gives no
first-use speed credit to such a conversion and shows no detector CPU
reduction from 10-bit data. Measuring the full benefit of a future
10-bit capture would require its own acquisition and verification
boundary.

The three arms ran once in order under the shared lock, on CPU 2
at nice 15 and I/O priority 7. The earlier low-bit pilot-bank screen
changed the detector algorithm. This assay kept the native receiver
and causal continuation code unchanged. Its attempted use of 8 bits
failed matched branch/continuation parity. The 10-bit result is a
bounded control, with numerical movement even on retained branches.
[Low-bit pilot-bank screen](low-bit-pilot.md)

Frozen experiment `dc19b71e1`. Five component tests cover the complete
signed CI16 value range, ties and saturation, truncation and bad
headers, and signed CFO/epoch branch matching. The [machine receipt](measurements/iq-block-float-0016.json.gz)
has uncompressed SHA-256
`3f60e8e33cadaf9e68a5f9870c7a930dcba89e4afba9317d33991e71de489745`.
