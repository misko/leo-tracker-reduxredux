# Reusable encoded allocation in the mapped original-frame reader

Reusing previously allocated private snapshot pages reduced the resident 78.3 MB read for DS30-0016 member 3 from **15.14–15.60 ms CPU to 11.56 ms CPU**. The first candidate allocation cost **15.48 ms**. All original signed sample spans and native detector outputs matched exactly. The one reused snapshot saved 3.8 ms versus the two control reads’ mean and retained 78.3 MB between requests. Neither the data copy into process memory nor the complete encoded SHA-256 was removed. [Frozen protocol](legacy-snapshot-reuse-protocol.md) · [Measurement receipt](measurements/legacy-snapshot-reuse-0016.json)

## Work at the existing boundary

The real all-member path already fills one private contiguous snapshot with `readv`, either from the bounded prefetch worker or at normal demand. It checks the original complete compressed digest in the installed `ShortWindowReader._member`. The mapped reader creates a NumPy view and lends its address to C, with no additional compressed payload copy. File-backed mapping would bypass that stable private snapshot. Read-only mapping still leaves the process exposed to modification after authentication or a fault on truncation by another writer.

Python calls `legacy_span` once per contiguous requested span. Each sparse exception may add one call by splitting a span. The exact full DS30-0016 run therefore made **at most 721** such calls for 713 admitted visits and eight exception intersections. The 4,746 ordinary requested blocks and 135 table-dependency blocks are processed in C. The archived 544.611 ms total span scope also includes actual decode, verified-window allocation, copies into returned arrays and requested SHA checks, so it cannot be charged to FFI. Map/decoder setup totaled 24.307 ms and detached map file reads 3.330 ms. Together, those facts leave no evidence of a large Python per-block bottleneck. [Full mapped reader audit](legacy-block-all-0016.md) · [Native span loop](legacy_block_seek.c) · [Pinned prefetch read routine](../../../tools/pipeline_eval/variants/experimental/receiver_ingress.py)

The whole run's 11 speculative reads copied 834,805,982 bytes in **174.640 ms worker CPU** with **0.058 ms** cumulative exposed demand wait. Its 13 mapped authentication scopes took 244.770 ms CPU including full-frame hashes and demand-read work. Those scopes have different denominators. Even deleting all recorded speculative read work would free at most 174.640 ms CPU in that part of the archived run. The actual warmed-slot estimate is on the order of **46 ms CPU** for 12 hypothetical reuses at the observed per-member rate, before any larger-slot allocation, fallback, synchronization or changed scheduling. The two-recording prepared child clocks need roughly 0.408 s less elapsed for the 1.6× summed threshold alone. The resident demand-read number does not establish a through-exit gain or predict cold storage. [Original physical timings](legacy-block-all-0107.md)

## Measured member

Both arms used the pinned prepared exception map from the actual all-member run, identical released manifest/index/encoded verification, and the same native 20/8 ms callback with the established member-local schedule. The trial calls the pinned prefetch descriptor routine synchronously in both arms. Read scope covers open, one complete snapshot copy and the original descriptor checks. Authentication includes that read, original complete compressed SHA and the native buffer view. The reader plus detector clock additionally covers map lookup, index authentication, signed span reads, detector callbacks and their comparison digest work. The shared preflight, pinned native loading and prototype source construction sit outside those member clocks. No asynchronous read or whole-recording schedule was modeled. All three named source files’ 19,166 pages were already resident and every run recorded zero filesystem input blocks and major faults.

| Order | Snapshot read CPU ms | Encoded authentication CPU ms | Complete member CPU / elapsed ms | Process minor faults |
| --- | ---: | ---: | ---: | ---: |
| Control fresh | 15.140 | 32.473 | 211.334 / 211.352 | 4,630 |
| Candidate first | 15.479 | 32.678 | 197.097 / 197.101 | 1,668 |
| Candidate reused | 11.558 | 28.890 | 197.205 / 197.231 | 865 |
| Control fresh | 15.600 | 32.892 | 199.495 / 199.508 | 1,585 |

The large first pair’s complete-member difference comes from work outside the measured read, whose first candidate was marginally slower. The reverse pair’s complete-member difference was 2.29 ms CPU versus 4.04 ms in the read itself. This experiment singles out the recycled destination's faults and copy time, with two fresh reads and one actual reuse. It offers no estimate of repeat variance.

Every arm issued the 64 original opportunities and carried seven matching exclusions. The 57 admitted visits decoded 44,160,000 requested bytes under eight full and 49 short requests. The controls and candidate reproduced the earlier independently frozen member-local 114 raw lanes, 38 positive lanes, three residual candidates, and exact requested sample and selected probe digests. They each decoded 382 requested ordinary blocks plus 11 dependency blocks, using 166,400 exact bytes in two sparse exception intersections. Flipping the last encoded byte in a private leased buffer reproduced the installed original-member digest refusal before the native decoder could open or emit any window. The original files were left untouched. [Earlier independent member verification](legacy-fused-map.md)

The proof of concept lends one bounded slot only while no previous buffer view remains. A NumPy descendant's exported view continues to pin the original lease. A concurrent request, excess size or closed slot uses ordinary allocation. Prefetch can require two live snapshots, so a single-slot demand result cannot claim that both workers would reuse an allocation or retain the same memory profile. Three component tests pass for lifetime and concurrent fallback, size and close bounds, and original descriptor checks. No runtime port was changed outside the research checkout. [Implementation](legacy_snapshot_reuse.py) · [Tests](../../../tests/pipeline_eval/test_legacy_snapshot_reuse.py)

## Reproduce

Supply the existing resident staging paths and a fresh private output. The first invocation resolved one historical report import before finding its companion directory on `PYTHONPATH`, so it ended before the input or measurement boundary. The corrected invocation ran the sole four-arm comparison.

```bash
repo="$PWD"
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
flock -x -w 30 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 sudo -n -u leo env TMPDIR=/dev/shm \
  OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$release/src:$payload:$release:$repo:$repo/reports/ALGO08/v3" \
  timeout 36s "$release/venv/bin/python" -Bm reports.ALGO08.v3.legacy_snapshot_reuse_trial \
  /dev/shm/legacy-snapshot-reuse-fresh.json
```

The as-run machine receipt has file SHA-256 `18845590874be2fb10682ee706698225216ab866eec586ff7f3a63ac3d49ddbb`.
