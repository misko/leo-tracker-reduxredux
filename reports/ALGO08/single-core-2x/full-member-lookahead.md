# Bounded read-ahead with DS30-sized compressed members

Two 16 MiB hints saved a median **222 ms of acquisition elapsed time** on a private 235.7 MB recording that began with empty file cache. All three cold pairs improved, and each arm was charged for the same full input. The result shows that the smaller fixture's overlap persists at full member size. Warm arms charged zero bytes, and their apparent elapsed gain tracked CPU differences. Raw-to-web speedup remains unmeasured. [Paired timing, cache and integrity receipt](measurements/full-member-lookahead.json)

| Compressed file cache at launch | Pairs | Median acquisition elapsed, control → hint | Median paired elapsed saved | Median paired CPU saved | Median paired non-CPU time saved |
|---|---:|---:|---:|---:|---:|
| Empty on every file | 3 | 2.386 → 2.059 s | 221.6 ms | −49.5 ms | 340.0 ms |
| All 57,540 pages present | 2 | 1.795 → 1.742 s | 52.9 ms | 53.8 ms | −0.9 ms |

Cold elapsed gains were **992, 222 and 158 ms**, including a candidate-first pair. Each of the six cold arms charged **460,320 blocks**, or 235,683,840 bytes, the exact page-rounded compressed inventory. The timed hint calls together took 8.1–9.9 ms cold and 0.34–0.36 ms warm. All ten timed acquisitions and the preload reproduced the same raw authority, ordered probes, complete detection digest and **282 selections**. The trial consumed **2.592 GB** of logical compressed input including preload, and the temporary fixture was removed afterward.

The two hints covered 14.2% of the fixture's compressed bytes, versus complete-next-file coverage in the earlier small-member test. Existing DS30 inventories allow up to 92 hinted prefixes across 106 members. Each segment's first member uses demand reads. The larger fixture provides evidence for cold acquisition overlap with the existing cap. The three cold repetitions on one generated fixture do not identify the attainable overlap on a historical recording or its effect on the complete solver and publication. [Small-member comparison](receiver-member-lookahead.md) · [Recorded DS30 storage variation](storage-io-accounting.md)

## Geometry and cache control

The DS30-0016 first-segment manifest supplies certified sizes of 78.55, 78.46 and 78.74 MB for three 64-window compressed members. Each member contains 102.4 MB of decoded stereo CI16. The bulk XFS volume has reflink disabled. The fixture therefore uses generated I/Q and the saved manifest's geometry. Four separate generated windows choose a fixed, whole-waveform scale to match compressed size using the same writer and compression level. The final recording contains 192 independently seeded generated windows and its three resulting files were each 78.56 MB. It reads only the certified source manifest from the original capture. [Fixture and benchmark](full_member_lookahead_trial.py)

The two arms run the released acquisition caller with the frozen `dd2d83a8` full two-scan detector, one-buffer compressed input and paired decoded SHA-256. The hint counts in the acquisition clock. Two 16 MiB hints cover the beginnings of the second and third files. The fixture is the same for every arm. File-specific cache advice applies only to its temporary, inode-checked compressed files. `cachestat` verifies all three are empty before each cold arm and complete before each warm arm. Linux task I/O counters record bytes charged to acquisition. The repeat setup warms the detector and the privately written extents, so cache-empty here refers to Linux file pages. Lower LVM and RAID cache state is outside the observation. [Existing hint](../../../tools/pipeline_eval/variants/experimental/receiver_member_lookahead.py) · [Task I/O interpretation](storage-io-accounting.md)

## Reproduction

The runner was frozen at `3eb01ab16` with the existing hint and cache shim and a checked copy of the earlier full-phase bundle's tools. The run was one Gauss lock holder with CPU 2, low CPU and I/O priority, and one numerical thread. The reference manifest and build specification are verified against the supplied file digests. Stage the source manifest byte-for-byte in the isolated research directory as `reference-manifest.json`.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
frozen="$bench/full-member-lookahead-3eb01ab16"
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 120s \
  env PYTHONPATH="$frozen:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.full_member_lookahead_trial /srv/bulk/leo-dev \
  "$frozen/reference-manifest.json" 1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc \
  "$bench/integration-full-float-phase-signed" \
  c8d1020e20b29c2c98359d74d72f3c799a66c22bff4ac5230a727213c5639546 \
  "$bench/ds30-cache-residency.so"
```

Eleven targeted tests passed. They cover exact reference-digest and geometry checks, per-arm cache-state validation, preservation of the original generated array during scaling, scoped hinting, the 16 MiB cap and canonical reader errors. [Fixture tests](../../../tests/pipeline_eval/test_full_member_lookahead_trial.py) · [Existing hint tests](../../../tests/pipeline_eval/test_experimental_receiver_member_lookahead.py)
