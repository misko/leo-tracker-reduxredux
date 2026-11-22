# Reusable Zstandard output in chronological ALGO08v2 acquisition

Across these two 128-visit prefixes, the direct decoder saved **26–39 ms of mean full acquisition CPU**. It used two 102.4 MB destinations. Savings were consistent on the physical input and more variable on public north. The frozen publication candidate retains its reviewed ingress. [Measurements and freeze manifest](measurements/zstd-conditional-acquisition.json)

| Saved source | Destination state | Full acquisition CPU, stream → arena | Verified reader CPU, stream → arena | Acquisition elapsed, stream → arena |
|---|---|---:|---:|---:|
| DS30-0016 physical | Fresh | 0.954 → 0.924 s | 0.266 → 0.246 s | 0.986 → 0.939 s |
| DS30-0016 physical | Reused | 0.942 → 0.903 s | 0.264 → 0.230 s | 0.960 → 0.922 s |
| Northern public simulation | Fresh | 0.921 → 0.887 s | 0.304 → 0.278 s | 1.195 → 1.193 s |
| Northern public simulation | Reused | 0.866 → 0.840 s | 0.282 → 0.260 s | 0.885 → 0.858 s |

The paired CPU savings ranged from 25 to 37 ms for fresh physical arenas and 26 to 56 ms for reused physical arenas. On the simulation, the ranges were 4 to 90 ms fresh and −18 to 64 ms reused. The 128 scheduled physical windows included 116 admitted visits and 12 exclusions, and all simulated visits were admitted. The 32 timed acquisitions matched the raw authority, ordered factors and complete detections hashes within each source. Both chunks used direct decoding in every candidate run, with two allocations in fresh runs and two arena reuses in warmed runs. The timed boundary ends at detector output.

## Scope and ownership

The chronological conditional-residual receiver completes both antennas while each window is current. This removes the immutable snapshot cost that dominated the earlier deferred receiver trial. Both benchmark arms used the released acquisition caller, reviewed conditional receiver and paired decoded SHA-256. Each source contributed its first two complete 64-window sealed chunks. The acquisition interval covers compressed reads, integrity checks and ordered detector output. The benchmark also compares the complete detection document digest. [Earlier deferred-reader measurements](zstd-arena.md) · [Acquisition harness](zstd_acquisition_trial.py)

The serial adapter keeps two destinations. A read-only buffer export stays live as long as a NumPy array or its derived view refers to it. An occupied slot is ineligible for reuse, so retaining both loans causes the following chunk to use the canonical streaming reader. The destinations add up to 204.8 MB on these inputs. Process RSS peaks include other arms run in the same process and cannot isolate the reader's memory delta. The native decoder accepts just one complete frame of the intended compressed and decoded extent. Decode problems go through the original reader. The original generator retains its compressed-member, index, window and full chunk checks, including validation beyond the last yielded window in a clipped range. The 61 targeted tests include retention across chunks and after context exit, and equivalent full and partial iteration on corrupt and concatenated frames. [Arena adapter](../../../tools/pipeline_eval/variants/experimental/receiver_arena_ingress.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_arena_ingress.py)

## Reproduction

The harness was frozen at research commit `cd27fcb66` on a private copy of the reviewed conditional candidate's `tools` directory. The copied modules were checked against that candidate's source manifest before timing. The pinned release supplies `leo` runtime code. The harness pins the scoped recording manifest, detector, both pilots, SHA-NI verifier and libzstd. Gauss runs used one low-priority pinned CPU and one numerical thread. A common preload warmed the receiver and file cache. Four paired runs per condition alternated arm order. Fresh arenas included first-touch page costs and reused arenas carried over resident destinations from a warm-up on the same chunks.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
base="$bench/integration-conditional-residual-reviewed"
frozen="$bench/conditional-zstd-cd27fcb66"
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$frozen:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.zstd_acquisition_trial \
  "$recording" "$manifest_sha256" "$release/assets" "$base/receiver.so" \
  --paired "$base/paired-sha256.so" cb8a3f9f88e608a04744c7776c22cb5d31b063e43cd1af657951b90adfe3e933 \
  --zstd /usr/lib/x86_64-linux-gnu/libzstd.so.1 060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80 \
  --first "$first" --repeats 4
```

Use `first=arena` for DS30-0016 and `first=stream` for public north. Insert `sudo -n -u leo --` before `env` for the physical source.
