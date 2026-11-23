# What two physical members spend on reading, verification and DSP

On two consecutive physical DS30-0008 members, the released descriptor consumed **47.75–49.04 ms CPU**. Complete authenticated traversal without detection consumed **272.76–274.84 ms CPU**. Adding the pinned full-20 ms and short-12 ms signed receiver brought CPU to **585.58–601.23 ms**, including **309.50–319.05 ms** in native calls. All six passes started with zero payload pages resident and each was charged the same **154,726,400 process input bytes**. Read-only elapsed still swung from **216.76 ms to 2,298.25 ms**. Identical filesystem page counts and input bytes did not establish identical storage service. [Frozen protocol](physical-stage-envelope-protocol.md) · [Full receipt](measurements/physical-stage-envelope.json.gz)

| Run order | Scope | CPU ms | Elapsed ms | Elapsed minus CPU ms | Compressed descriptor elapsed ms | Effective compressed MB/s for the scope |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Read | 47.75 | 2,298.25 | 2,250.50 | 2,297.60 | 67.32 |
| 1 | Read and verify | 272.76 | 901.87 | 629.11 | 676.85 | 171.56 |
| 1 | Read, verify and DSP | 585.58 | 817.44 | 231.86 | 280.12 | 189.28 |
| 2 | Read, verify and DSP | 601.23 | 795.54 | 194.31 | 234.82 | 194.49 |
| 2 | Read and verify | 274.84 | 797.95 | 523.11 | 574.42 | 193.90 |
| 2 | Read | 49.04 | 216.76 | 167.73 | 216.03 | 713.78 |

## Bytes, placement and clocks

The original members contain **154,722,097 compressed**, **345,429 index**, and **204,800,000 decoded bytes**. Their original manifest is 6,812 bytes. The private XFS payloads started at zero of 18,907 and 18,868 pages and finished fully resident. Both index files held all 43 pages throughout. `/proc/self/io` reported the same payload-page-rounded read charge in each arm, matching 302,200 `ru_inblock` units. The six attempts charged **928,358,400 process input bytes**. Process-charged reads are bytes fetched below the file cache. Downstream tier and drive cache behavior was uncontrolled. The table uses decimal MB and the logical compressed sizes. The DSP scope processed **250.54 and 257.44 decoded MB/s**. There were no advisory lookahead calls. Point measurements apply to this serial demand path on this copy. [Scoped runner](physical_stage_envelope.py)

The descriptor CPU stayed between 47.09 and 51.36 ms across the arms. In the matched verify-only arms, Zstandard reads consumed **135.84–136.26 ms CPU** and paired decoded SHA-256 consumed **46.93–47.13 ms CPU**. Subtracting descriptor CPU from the encompassing compressed verification spans gives **33.87–34.23 ms CPU** for the remaining compressed authentication. The complete callback consumed **312.04–322.12 ms CPU**, including the native calls. The remaining elapsed spans include storage waits and scheduling. The raw task delay accounting switch was off, and per-process runqueue deltas of **0.05–10.54 ms** account for a smaller share of the measured non-CPU time. Descriptor non-CPU time covered **186.73–231.82 ms** inside the actual DSP runs. Subtracting one arm's elapsed from another would misattribute storage service to decoding or DSP in this sample.

The first launch hit its 75-second outer timeout during staging after writing both private payloads, before timing any arm. The measured launch reused these exact private files and copied zero additional source bytes. Both digest-verified scopes then authenticated the staged content. Staging elapsed therefore has a censored first-launch bound and is outside the table. Only the private payload files received file-cache advice. No original files or QNAP paths were modified. [Recovery freeze at `d0d52f019`](physical-stage-envelope-protocol.md)

## Input and receiver identity

The descriptor-only arm read the declared extents with stable descriptor guards and discarded them. Each authenticated arm used the released reader to check the pinned manifest, both signed indexes and compressed SHA-256 values, all 128 decoded I/Q digests, both whole-decoded digests, and length and trailing bytes. The resulting raw authority and 256 original probe metadata rows matched independently saved published input. The verification-only arm emitted empty candidates. Each DSP arm executed **32 full and 224 short** native lane calls and reproduced the same **136 signed factors** from the existing complete raw candidate, with byte-equivalent ordered probe content and original delivery clocks. The runner compares the signed sorted probe content digest `55de6c9ff35b16b72f536acfa0e234362d15699acdca2c838caef4809d17f612`. [Component tests](../../../tests/pipeline_eval/test_physical_stage_envelope.py) · [Prior signed dense acquisition](dense-full-short-raw.md)

The previous three-member resident experiment saw **about 400 ms CPU outside native DSP** over 192 visits. The new DSP arms spend **276–282 ms outside native DSP** over 128. These independent samples have comparable per-visit CPU scope. The earlier full dense candidate remained **20.49 elapsed seconds above half the archived stock wall time**. At its published solve and native work, the authenticated-input audit priced **204.7 effective compressed MB/s over the total acquisition budget**, or **365.7 MB/s through the after-native remainder** for the complete recording. Both serial two-member DSP scopes here ran below that first rate. The rate comparison gives scale only. The 106-member recording has varying compression, capture contents, cache residency and service, and its released route hints ahead. There was no full raw pass, solve or publication in this comparison. [Resident stage attribution](dense-ingress-attribution.md) · [Recording byte and time budget](authenticated-input-coverage.md)

## Reproduction

Use a fresh output directory on tmpfs, the original storage-read account and the existing private local XFS research area. The runner validates source and binary digests. Six owned tests and ten adjacent tests passed.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 timeout -k 4s 75s \
  env PYTHONPATH="$PWD:$release/src:$release:$payload" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.physical_stage_envelope \
  /srv/bulk/leo-dev "$short" /dev/shm/physical-stage-reproduction
```
