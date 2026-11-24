# Original stereo visits attested from the preserved partials

The preserved DS30-0163 and DS30-0419 compressed prefixes yield
**29 and 15 individually authenticated original stereo visits**.
The extractor used only existing private tmpfs bytes and the
original signed manifest and index for each case. The original
full-member staging results remain unscored. No detector, solver,
new acquisition or backing payload read entered this check.
[Frozen method](partial-window-attestation-protocol.md)

| Scope | DS30-0163 | DS30-0419 |
| --- | ---: | ---: |
| Staged compressed bytes supplied | 35,651,584 | 18,874,368 |
| Detached issued visits | 29, sequences 0–28 | 15, sequences 0–14 |
| Detached decoded bytes | 46,400,000 | 24,000,000 |
| First incomplete visit | 29 | 15 |
| Unattested decoded bytes from that visit | 130,560 | 248,320 |
| Signed original sample-counter span | 1.2591446 s | 0.6406300 s |
| Installed validity-policy admits, from signed metadata | 26 | 9 |
| Extract and cross-check wall | 0.256 s | 0.112 s |

The verified staged prefix digest matches the frozen checkpoint in
each case. The unchanged signed manifest binds the original first member
and its index. The extractor parses all 64 original signed index rows,
checks contiguous raw offsets, stereo shape and original counters, and
compares SHA-256 for each complete emitted visit in order. Both the
Python incremental decoder and the separate system Zstandard decoder
emitted identical bytes, including the portion of the next row. The first
decoder reported no frame EOF. The CLI reported a premature end. Each
partial next visit would require 1,600,000 bytes and was left out of the
detached file. The incremental API reported no exposed unused or
unconsumed encoded tail after all staged bytes were supplied.

A separate local pass reopened the detached file and rehashed every
row. It applied the installed validity policy using the signed sample
shapes. DS30-0163's issued list retains excluded visits **0, 22, 26**,
including the original hardware anchor on visit 0. DS30-0419 retains
excluded visits **4, 5, 6, 9, 12, 14**. The validity pass changes no
attested visit boundary.

Each detached witness records original session and inventory authority,
the manifest and index hashes, clock bracket, receiver IDs `(0, 1)`,
10 MS/s rate, and ordered index rows with target, acquisition counters,
byte ranges and original IQ digests. The privately detached byte files
contain only the verified whole visits. The receipts mark whole
compressed digest, frame checksum and normal acquisition acceptance
as unverified. This visit witness introduces no recording product.

| Case | Detached CI16 SHA-256 | Visit witness SHA-256 |
| --- | --- | --- |
| DS30-0163 | `14859a43ff7ef78e502d16d203ce111b836f3f30aa92a605b6bc36fd507c3116` | `f97a78dc990d406237a1c896c1c26d7ce04ce8162722a61b2d01c98ca8c5dd6e` |
| DS30-0419 | `c213e943542524289a206d3c6c0a7d67b1939b4cddeb8b4ea066d5c40494bd4b` | `7c50973d2ccc1b16dd59c0019aafb90306b406a94f3f4144e306e339e71fb19c` |

The witness and CI16 files are in the private sibling directories
under `/tmp/leo-ds30-partial-window-attestation01`, named
`visits.json` and `verified.ci16`. The extractor code froze at
`3316c244de52ef53f0598c67f8383517eb628db2`. The machine summary
contains the ordered attested spans and hashes without waveform data.
[Extractor](partial_window_attestation.py) ·
[Tests](../../../tests/pipeline_eval/test_partial_window_attestation.py) ·
[Machine receipt](measurements/partial-window-attestation.json),
SHA-256 `9d7d8f180328a200d63e4cfbef342f31f669dff0d32ea1d28aa924d51bdfadb0`.
