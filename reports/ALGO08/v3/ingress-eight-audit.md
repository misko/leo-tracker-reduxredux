# Where the complete 20/8 ms physical reader spends time

One resident signed DS30-0169 member took **296.928 ms CPU and
305.541 ms elapsed** from installed acquisition entry through its sealed-input
packet construction. The two native apertures used **127.593 ms CPU**.
Of the remaining **169.334 ms**, Zstandard read, compressed authentication
and paired decoded SHA-256 took **118.911 ms**. Compressed descriptor,
allocation and transfer took another **36.049 ms**. All other work totaled
**14.373 ms**, including decoder-independent view construction, source
validation, the native context and unassigned time.

| Disjoint acquisition stages | CPU ms | Elapsed ms |
|---|---:|---:|
| Original compressed descriptor and transfer | 36.049 | 36.053 |
| Remaining compressed SHA and framing | 17.480 | 17.480 |
| Signed manifest and identity | 0.430 | 0.432 |
| Index check and JSONL parsing | 0.901 | 0.903 |
| Zstandard read and owned decoded bytes, 65 calls | 77.609 | 77.702 |
| Zstandard setup | 0.007 | 0.008 |
| 64 paired window and full-member SHA updates plus finalize | 23.822 | 30.883 |
| NumPy views of decoded bytes, 64 calls | 0.289 | 0.304 |
| Retune parsing, admission and packet authority digests | 1.352 | 1.573 |
| Detector context entry and callback excluding native | 7.462 | 7.413 |
| Native 20 ms full, 16 lanes | 52.911 | 52.941 |
| Native 8 ms short primary, 86 lanes | 74.683 | 75.724 |
| Remaining orchestration and measurement | 3.932 | 4.125 |
| **Complete acquisition** | **296.928** | **305.541** |

The table uses rounded exclusive times. Compressed transfer is subtracted
from its encompassing member-verification span. Both aperture clocks are
subtracted from the Python callback. Paired SHA updates compute the
independent window digest and advance the complete-member digest in one
installed native call. The member finalize took 0.006 ms. Process elapsed
through exit was **2.315 s** and CPU **2.301 s**, including setup, pinned
runtime checks, historical packet comparison and output audit. The archived
same-fixture acquisition took **261.073 CPU / 262.963 elapsed ms** with
**120.260 ms** native CPU. The profile alone supplies attribution and no
timing gain. The two runs used different observers.

## Which bytes the detector actually needs

The 64 issued opportunities contain 51 admitted stereo visits. The eight
full visits expose 12.80 MB of 20 ms samples and 43 short visits expose
27.52 MB of 8 ms samples. The short tails account for **41.28 MB** and the
13 rejected visits another **20.80 MB**. This leaves **62.08 MB of the
102.40 MB decoded** outside the native apertures. All **78,852,856 compressed
bytes**, the signed 173,459-byte JSONL and 6,812-byte manifest stayed resident.
The new process recorded zero input blocks and major faults.

All 64 released Zstandard reads already return a Python-owned bytes object.
The installed NumPy view retains that identical object and does not allocate
a separate payload. The view's reshape and the existing native callback
consume the same backing address. The profile counts Python view work
separately. Its decoder span still includes any native decoder-internal
copies and constructing the owned bytes, so it cannot assign the entire
77.609 ms to decompression alone. The 62.08 MB outside the detector still
feed the authenticated per-window and whole-decoded SHA checks, retaining
the original continuous Zstandard history and framing. Dropping them at
decode would change the input contract.

The packet and every native lane tuple matched the archived 20/8 ms
measurement. The replay preserved all 64 ordered input hashes, both member
hashes and window/framing checks, original opportunity order and clocks,
and all selected ranks, epochs, signed CFOs and scores. No new staging,
cold source read or numerical solve ran. [Archived independent member](independent-8ms-0169.md)

## Removable work

No distinct current-format proposal passed the predeclared **25 ms/member**
screen. A view or other detector-independent change outside compressed
transfer, decode and payload SHA could save at most the full 14.373 ms in
this witness. An isolated transfer change would have to remove about
69% of its span, or an isolated decoder change about 32%. A single
resident observation leaves room for a different implementation. It
does not supply a saving for it.

The earlier system-libzstd comparison isolated 9.36–9.83 ms/member from
decode. Fused direct blocks saved up to 12.94 ms/member outside native
DSP, including a change to that same decoder backend. Those figures
overlap. The bounded ring chiefly reduced RSS, and the original
allocation, pooled descriptor and index batching experiments did not
establish comparable savings. An existing mutable pathname mapping
would also lose the release's private stable compressed snapshot.
Eliminating a hypothetical independent copy of every unused byte does
not describe the executed detector path, which already uses a view.
[Measured backend](dense-zstd-backend.md) · [Fused blocks](fused-block-input.md) · [Bounded ring](fused-window-ring.md) · [Allocation audit](decoded-allocation.md) · [Index and descriptor attribution](dense-ingress-attribution.md)

As a scale comparison, repeating the prior 12.94 ms/member saving at a
constant rate would save about **0.163 s** over 808 visits. This is a
model, not a DS30-0016 timing. The weak all-visit run has **1.732 s**
measured outside native acquisition and a **1.895 s** modelled gap to
half of named v3. Even granting all non-native acquisition for free
leaves **0.163 s** of that modelled gap with its measured native and
publication scopes intact. A faster framing design could still be useful
for future captures. It needs an independent writer-to-reader test and
cannot retroactively remove verification from the signed DS30 files.
[Full weak budget](weak-all8-combined.md)

## Reproduce

The [protocol](ingress-eight-audit-protocol.md) was frozen at `3546e875b`.
The [observer](ingress_eight_audit.py) ran at `12c15c960`, using
`python -BPs -m reports.ALGO08.v3.ingress_eight_audit launch FRESH_TMPFS_ROOT`
under the existing low-priority Gauss CPU2 lock, with the pinned release
and checkout import paths and one numerical thread. Three component tests
passed. The [receipt](measurements/ingress-eight-audit.json.gz) holds all
exact scopes, source pins and signatures.
