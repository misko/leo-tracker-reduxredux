# One SHA-256 message schedule for both decoded I/Q digests

Sharing a SHA-256 message schedule saved about **17 ms of reader CPU per 64-window chunk** on both physical prefixes and a public northern simulation. All three still verified the original index and compressed member, every window, and the complete decoded chunk. Each returned the same 40 requested window records. The other 24 windows still took part in verification.

| Saved first chunk | Compressed buffer reader CPU | Paired SHA-256 reader CPU | CPU saved |
|---|---:|---:|---:|
| DS30-0016 physical | 145.80 ms | 128.23 ms | 17.57 ms |
| DS30-0374 physical | 145.57 ms | 128.96 ms | 16.61 ms |
| Northern simulation | 149.51 ms | 132.37 ms | 17.13 ms |

Each timed chunk contained 64 windows of 1,600,000 decoded bytes, totaling 102.4 MB. The table gives the median of three matched pairs, with arm order reversed between pairs. Both arms used the existing compressed input buffer. Independent hash-only timings on synthetic buffers of the same size measured **42.97 ms** to compute both digests with `hashlib`, **25.02 ms** with the paired kernel, and **21.83 ms** for the cumulative hash alone. [Physical reader receipts](measurements/paired-sha256-sealed.json) · [Simulation receipt](measurements/paired-sha256-public.json) · [Hash-only receipts](measurements/paired-sha256-synthetic.json) · [Initial bound](measurements/paired-sha256-hashlib.json)

Scaling by the sealed decoded byte totals gives about **0.22 CPU seconds** for DS30-0016's 808 windows and **1.76 CPU seconds** for DS30-0374's 6,770 windows. These are reader-stage projections from one measured chunk per recording. Acquisition, positioning and publication were outside the timed interval, and the trial uses existing recordings.

## Digest behavior

The x86 SHA-NI kernel expands each aligned 64-byte decoded block once. It applies the standard SHA-256 rounds to independent window and chunk chaining states. OpenSSL buffers partial blocks, handles a window that starts inside a chunk block, and finalizes each message with its own padding and length. The original reader still owns decompression, window order, geometry, lengths and comparison to the persisted digests. The context falls back to the release verifier on a host where the library or SHA-NI instructions are unavailable. The opt-in launcher retains the existing compressed buffer in that case. [Kernel](../../../tools/pipeline_eval/variants/experimental/paired_sha256.c) · [Reader binding](../../../tools/pipeline_eval/variants/experimental/paired_sha256.py)

The native tests compare independently computed hashes on empty windows, unaligned pointers, mixed partial states and inputs straddling SHA-256 padding boundaries. The reader tests compare returned samples and failure order for damaged compressed and index members, short frames, surplus decoded bytes, and digest or geometry failures in the remainder of a requested prefix. The launcher tests exercise native selection, the unsupported-hardware path, and rejection of altered library bytes. [SHA-256 tests](../../../tests/pipeline_eval/test_experimental_paired_sha256.py) · [Launcher tests](../../../tests/pipeline_eval/test_paired_publication.py)

## Reproduction

Compile the isolated library with the Gauss C compiler and OpenSSL development headers. The pinned build used GCC 15.2.0 and OpenSSL 3.5.5. Its SHA-256 is `cb8a3f9f88e608a04744c7776c22cb5d31b063e43cd1af657951b90adfe3e933`. The kernel uses the OpenSSL low-level `SHA256_CTX` interface available in that build. The frozen bundle records hashes for the C source, Python binding and compiled shared object. The launcher verifies the binary before copying its exact bytes to the process-private asset directory. [Freezer](../../../tools/pipeline_eval/qualification/freeze_publication.py)

```sh
cc -fPIC -shared -O3 -std=c11 -Wall -Wextra -Werror -Wno-deprecated-declarations \
  tools/pipeline_eval/variants/experimental/paired_sha256.c -o "$paired_library" -lcrypto

python -m tools.pipeline_eval.qualification.freeze_publication "$bundle" "$receiver" "$receiver_sha256" \
  --solver shared-tables --schedule deferred --startup lazy-exports --rendering raster-layout \
  --ingress paired-sha256 --paired-sha256 "$paired_library" "$paired_sha256"
```

Run `paired_sha256_trial.py --native "$paired_library"` for the hash-only comparison. For the physical reader comparison, add `--bulk /srv/bulk --binding "$ds30_0016_binding" --binding "$ds30_0374_binding"` and use the release service account. For the public simulation, add `--manifest "$north_manifest" "$north_manifest_sha256"`. Use the released runtime, CPU 2, one numerical thread and the shared Gauss lock at low CPU and I/O priority. [Benchmark harness](paired_sha256_trial.py)
