# Isolated read-ahead on a resident northern simulation

With the same full-coverage 20/12 ms receiver and decoder, one-member read-ahead **added 191.19 ms** of acquisition elapsed in one order and **saved 3.70 ms** in the reverse order. Both routes produced identical signed detection bytes. The resident tmpfs comparison shows no repeatable acquisition gain. The blocked physical DS30-0008 comparison remains unmeasured. [Prespecified control](public-short-prefetch-protocol.md) · [Matched receipt](measurements/public-short-prefetch.json.gz)

## Exact input and verified output

The input is the saved northern public development recording `0abe7b4514be674d9f5388e3`. Its V2 seal identifies two antennas at **10 MS/s**, with 200,000 native IQ samples per antenna per stereo visit. The first three complete adjacent members contain **192 visits**, **253,648,458 compressed bytes**, and **307,200,000 decoded bytes**. The original containing offer is the 25 km square centered at **47.77225055380364°, 16.262555402252783°**. It was read and checked against its original receipt. Acquisition ends before geographic scoring and does not consult the offer.

All four runs admitted all 192 visits, made **48 full 20 ms calls and 336 short 12 ms calls**, and issued **182** signed factors. The native code followed each RF stream from its first visit. Each arm passed the compressed, index, per-window IQ and decoded-member digests. Its 384 probe rows, 192 original delivery clocks, and hardware anchor equal the corresponding prefix of the separately sealed genuine full-short result. The scoped packet SHA-256 is `bd613c18794ea25ba4e3b8b7015a722d167a443ccf0a04eeb51b52bf902fc41d` in all four cases.

## Resident acquisition

| Pair order | Compressed input | CPU / elapsed s | Elapsed less CPU ms | Compressed / decoded MB/s | Peak RSS MiB |
|---|---|---:|---:|---:|---:|
| 1, first | Installed advisory hints | 0.9780 / 0.9787 | 0.704 | 259.2 / 313.9 | 417.0 |
| 1, second | One-member prefetch | 1.1686 / 1.1699 | 1.255 | 216.8 / 262.6 | 416.9 |
| 2, first | One-member prefetch | 0.8776 / 0.8780 | 0.409 | 288.9 / 349.9 | 417.3 |
| 2, second | Installed advisory hints | 0.8812 / 0.8817 | 0.473 | 287.7 / 348.4 | 416.8 |

Each worker ran on CPU 2, including the candidate's one helper thread. All four arms began and ended with **61,927** resident compressed pages and charged **zero** filesystem input/output blocks and zero `read_bytes` and `write_bytes` in process I/O accounting. Each returned 254,745,016 logical read bytes across the measured and seal scopes, including non-payload reads. The rates in the table divide signed compressed and decoded sizes by acquisition elapsed. Temp staging, process startup and the approximately 2.3 ms immutable packet seal are outside acquisition.

The worker supplied **169,392,487 bytes** from two future members per candidate, with two hits and no fallback. Its CPU time was **141.37 ms** in pair one and **32.67 ms** in pair two, included in the process totals. The measured demand wait was **14.78 and 13.65 µs**. Native receiver process CPU in the first prefetch arm was also higher than its advice arm. Those nested clocks can include concurrent worker CPU. Elapsed less process CPU stayed below 1.3 ms throughout. This setup leaves little exposed storage wait for prefetch to remove and measures no cold-device service.

The southern materialization stopped before copying or timing because five compressed pages were nonresident. The first northern advice measurement completed, but its validation initially selected a causal-filtered archived packet. The corrected comparison reconstructed the expected complete scoped document from the original maximum-margin archive, authenticated last index counter and the already finished arm's measured I/Q digests. Its reconstructed byte hash matched the sealed arm. That original clock was retained. The remaining three workers used a fresh private tmpfs copy of the identical manifest and members. Every worker independently passed the same residency and signed-output checks. [Runner and recovered receipt binding](public_short_prefetch.py)

## Relation to physical data

The 192 native windows occupy the same decoded size as the dense physical prefix, but the simulation uses **9.29% more compressed bytes**. Compressed/decoded fractions are **82.57%** for this simulation and **75.55%** for DS30-0008. Physical XFS request timing and the science, entropy and decoder mix can differ. The earlier physical same-aperture trial changed read-ahead and the decoded arena together. Its isolated storage effect remains open. [Physical XFS trial](full-short-arena.md)

## Reproduce

**28 component and adjacent tests passed.** A fresh run uses the saved original tmpfs inputs and records both matched orders without the archived recovery option. [Component tests](../../../tests/pipeline_eval/test_public_short_prefetch.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 75s \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.public_short_prefetch \
  run "$short" "$fresh_tmpfs_output"
```
