# Incremental block decode into verified receiver input

Direct Zstandard block delivery and native paired hashing reduced complete acquisition CPU by **16.65–22.72 ms** across two reversed comparisons on one authenticated DS30-0008 member. CPU outside the native receiver fell by **10.72–12.94 ms**. Both paths produced identical signed detections and retained all original input checks. The fused path used about **94 MiB** more peak RSS, and its decode stage did not improve on earlier timings from the same system libzstd through the ordinary streaming interface. [Frozen test](fused-block-input-protocol.md) · [Complete timing and authority receipt](measurements/fused-block-input.json.gz)

## Input path

The released short-window reader still authenticates the original manifest and index and checks the compressed member's length and SHA-256 before decoding it. For one standard dictionary-free frame within the bounded extent, the prototype drives system Zstandard's bufferless `ZSTD_decompressContinue` API. It gives each block the next contiguous address in one owned decoded destination and preserves all decoder history. When the requested window is complete, the same native call computes its SHA-256 and updates the independent member SHA-256 through the installed paired SHA routine. The released reader compares each returned digest with the original index before yielding a read-only CI16 view. It also checks the full decoded digest against the original manifest at member completion. Frame completion, exact compressed consumption, checksum processing and the declared decoded extent remain checked. Unsupported layouts enter the normal stream decoder and paired SHA path. Each decoded member owns its destination, so retaining a prior view does not allow a later member to overwrite it. [Native path](fused_block_input.c) · [Stock-reader binding](fused_block_input.py)

The prior native verify-only drain decoded through Zstandard's buffered streaming API into one scratch window and emitted no sample arrays on unpaid members. The earlier whole-member arena decoded all samples before checking or delivering its first window. This experiment instead writes each block directly to the destination and advances to the next consumer window only as needed. The destination still grows to the complete decoded member size. [Verify-only drain](native-verified-drain.md) · [Whole-member arenas](full-short-arena.md)

## Matched member observations

The member contains **77,442,779 compressed bytes**, **172,750 index bytes**, and **102,400,000 decoded bytes** spanning 64 original stereo windows. Every arm began and ended with all **18,907** private compressed pages resident. There was no eviction or advisory action on the original. The receiver made 16 full and 112 short native calls in each arm. Each file matched the previously sealed signed detection bytes at SHA-256 `856affd89c8d3effd46c766efd9d02919c14641ad6b9837f3dc685f9f757ba2e`. All 64 window digests and both member-level digest checks matched their original authority. Each fused arm processed one standard frame in **1,567** native input steps with no fallback. [Historical exact member witness](dense-zstd-backend.md)

| Pair order | Path | Decode CPU ms | Paired SHA CPU ms | Acquisition CPU ms | Acquisition elapsed ms | CPU outside native receiver ms | Peak RSS MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| 1, first | Release | 72.116 | 23.809 | 307.620 | 315.997 | 139.292 | 328.5 |
| 1, second | Fused blocks | 62.402 | 23.404 | 284.898 | 285.033 | 126.353 | 422.4 |
| 2, first | Fused blocks | 62.919 | 23.332 | 283.135 | 283.256 | 126.022 | 422.6 |
| 2, second | Release | 71.626 | 23.722 | 299.787 | 299.930 | 136.742 | 328.7 |

The release's decode clock includes returning a newly owned Python bytes object. The candidate's native decode and hash clocks are taken inside the bridge. They exclude its frame eligibility check, destination allocation, and Python view and digest handoff. Those costs still appear in complete acquisition. Original compressed descriptor CPU was **11.53–12.24 ms**, and compressed member verification including the descriptor cost **28.54–29.30 ms**. The measured native receiver span also fell **5.93–9.78 ms** on identical inputs. The paired clocks do not isolate whether delivery memory behavior contributed to that change.

The earlier system-libzstd streaming bridge took **61.56–61.80 ms** for its read spans and **126.47–128.48 ms** outside native receiver work on this same member, in a separate experiment. Those clocks overlap the present path closely. The current comparison includes both the library-build change and the fusion. It establishes a repeated verified acquisition gain against the installed Python binding and supplies no repeatable advantage over the previous system bridge. Resident complete acquisition throughput here reached **271.7–273.4 MB/s**. Process input blocks ranged from zero to 4,544 despite equal observed payload residency, with the largest charge in the first released arm. The durable detection seal after acquisition took **0.247–1.217 s** across the four arms and was not used to attribute gains. One-time staging took **22.15 s** outside the measurement. [System-streaming library comparison](dense-zstd-backend.md)

At the same per-visit rate the observed **10.72–12.94 ms** saving outside native receiver calls would translate to **1.13–1.37 CPU s** on the full 6,772-visit dense recording. This is a conditional transfer from one resident input, without cold service timings or a measured complete publication. The existing candidate is **12.800 CPU s** above half the historical stock clock. [Dense raw publication](dense-full-short-raw.md)

## Reproduce

Tests cover independently broken decoded window and full-member hashes, original compressed and index checks, concatenated-frame fallback, retained views and delivery of the first window before final member validation. **18 focused and adjacent tests passed.** The runner stages only the previously verified first member and seals the same document in both arms. [Runner](fused_block_input_trial.py) · [Tests](../../../tests/pipeline_eval/test_fused_block_input.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 100s \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.fused_block_input_trial \
  run /srv/bulk/leo-dev "$short" "$fresh_output"
```
