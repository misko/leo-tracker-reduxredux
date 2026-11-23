# Incremental compressed delivery and provisional signed DSP

Replaying measured arrivals from one staged DS30-0169 member, incremental delivery finished the first admitted stereo DSP **39.87 ms earlier** in both orders. Fully verified packet sealing improved by **11.40–13.61 ms**. Every successful seal matched byte for byte. Under a replay that releases all bytes at the previously measured cold-read completion, the seal improved by only **2.42–2.60 ms**. There is no submember cold arrival trace, so this establishes the staged replay effect and leaves cold throughput unmeasured. [Frozen scope](incremental-ingress-protocol.md) · [Arrival, DSP and seal clocks](measurements/incremental-ingress.json.gz)

## Transaction and delivery clocks

The prior fused ring bounds **decoded** history after receiving a fully authenticated compressed snapshot. This prototype instead rolls SHA-256 over compressed input objects of up to **1 MiB** as the original Zstandard stream asks for them. The released reader still validates the original index, validates each immutable decoded window against its own signed I/Q hash before DSP, and checks exact decoded length and the whole-decoded digest. The trial verifies complete compressed consumption, EOF, stable descriptor identity and original compressed SHA-256 before returning a packet. The provisional receiver and its scheduling state remain private to the acquisition call. They are discarded on error. [Prior ring experiment](fused-window-ring.md) · [Driver and commit boundary](incremental_ingress.py)

The source was the existing verified **78,852,856-byte** member-0 tmpfs copy. A single staged calibration delivered **76** compressed chunks, ready at **0.372–23.730 ms** relative to its first read. Those times are actual read completions, with each previous chunk's SHA update charged in the producer sequence. Calibration took **23.77 ms CPU** and ran once outside the comparisons. Each measured arm replayed those absolute readiness times, did its own real tmpfs reads and independently authenticated the payload. A bounded synchronous producer and consumer ran on the same CPU. The candidate did not use another I/O or numerical worker. [Calibration and resource counters](measurements/incremental-ingress.json.gz)

The immediate and cold-completion controls make all chunks eligible at once. The cold envelope uses **420.36 ms** from the original DS30-0169 member-1 descriptor receipt. That receipt records a whole read and provides no verified earlier byte arrivals. The staged whole arm uses the original single `readv` when all bytes become eligible at once, and length-bounded `readv` segments with the measured staged cadence. All arms charge the same signed input extent. [Original cold measurement](direct-storage-0169.md)

| Replay | Path | First owned window, ms | First stereo DSP finish, ms | Fully verified, ms | Packet sealed, ms |
|---|---|---:|---:|---:|---:|
| Immediate | Whole | 34.25–34.52 | 47.75–47.84 | 284.17–287.49 | 284.54–287.86 |
| Immediate | Incremental | 2.38–3.15 | 14.40–15.66 | 271.13–273.51 | 271.50–273.87 |
| Measured tmpfs cadence | Whole | 43.44–43.55 | 56.53–56.57 | 295.24–295.78 | 295.61–296.18 |
| Measured tmpfs cadence | Incremental | 3.67–3.68 | 16.66–16.69 | 282.19–283.86 | 282.57–284.22 |
| Cold completion only | Whole | 454.85–455.32 | 468.07–468.53 | 705.41–706.21 | 705.78–706.62 |
| Cold completion only | Incremental | 423.91 | 437.04–437.25 | 703.00–703.66 | 703.36–704.02 |

The table starts at the first compressed read request in each arm. The full scope clock also includes preparation and startup. The first immediate whole arm paid **717.15 ms** before compressed demand, during initial imports and setup. Its complete stopwatch was **1,005.01 ms**, and the reverse-order whole arm took **287.74 ms**. The table separates that first startup interval from comparisons at the data boundary. On measured arrivals, paired scope CPU was **289.67→286.83 ms** and **290.27→285.15 ms**. The whole reads slept about **9.11 ms** for paced availability. Incremental reads slept **0.43 ms**, with decode and DSP progressing after the first owned window. The candidate consumed its last compressed bytes at **277.79–279.41 ms** after demand because it pulled chunks as needed. Earlier provisional work did not make the packet authoritative sooner than the final seal. [Per-arm absolute and relative clocks](measurements/incremental-ingress.json.gz)

The 12 complete runs all verified 64 original I/Q digests, included 13 excluded visits and 51 admitted stereo visits, and reproduced the exact archived ordered 66 native factors and 56 selected factors. All sealed documents had SHA-256 `9e2d2228b87ed3317ad341e55b4a582871ef7d9d934cf3a1b31b542aa76bcdcc`. All 19,252 staged source pages remained resident and all 12 acquisitions charged zero input blocks. The compressed input limit is an allocation bound for an individual delivery object. Process peak RSS was shared across arms and provides no isolated memory-saving measurement. [Prior exact mixed packet](receiver-ceiling-0169.md) · [Scope and parity receipt](measurements/incremental-ingress.json.gz)

## Late failure

The test flipped the last checksum byte of an in-memory duplicate while leaving the staged source and manifest intact. The whole-read control rejected the compressed SHA-256 before exposing any window or running DSP. It used **35.80 ms CPU** and **44.81 ms elapsed**. The incremental path reached **63 individually verified windows** and **50 completed stereo DSP visits** before Zstandard rejected the checksum. It discarded all provisional work, including **144.63 ms callback CPU**, and emitted no packet. The full failed arm used **280.42 ms CPU** and **281.21 ms elapsed**. The direct feed tests also force a compressed hash mismatch after all bytes arrive, and the reader tests exercise both window and whole-decoded hash mismatches. [Failure accounting](measurements/incremental-ingress.json.gz) · [Component tests](../../../tests/pipeline_eval/test_incremental_ingress.py)

## Reproduction

The receipt SHA-256 is `a7223a238c11b0068dd9e3a94e6e27fff84a2c03728fc8a28ab5bca54ab72dd0`. Fifteen component and adjacent tests passed. The driver requires the previously staged source and writes only fresh tmpfs evidence. It performs no original archive read, new capture, solve or publication benchmark. [Runner](incremental_ingress.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.incremental_ingress \
  /dev/shm/leo-incremental-ingress-rebuild
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-incremental-ingress-rebuild-tests \
  tests/pipeline_eval/test_incremental_ingress.py tests/pipeline_eval/test_receiver_ceiling_0169.py
```
