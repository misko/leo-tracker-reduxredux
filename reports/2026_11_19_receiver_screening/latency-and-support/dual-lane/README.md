# Parallel native processing on two antenna lanes

Parallel execution reduced median fifth-center response from **32.05 to 19.64 ms**. Both decoded rows completed within 20 ms on **203/384** calls, compared with **0/384** in the serial dual control. Fifth-center p95 was 45.15 ms and p99 was 170.79 ms. The parallel response met the 20 ms target on just over half of these calls. Stock reached it on 293/384. [Native timing figure](dual-lane.png) · [Exact per-call clocks](native-timing.csv)

## Native dataflow and parity

The caller runs the first physical antenna. One persistent POSIX worker runs the second. Each lane owns its own FFTW plans, GLRT buffers, candidate result and one-lane scout. Both contexts and their FFTW plans are constructed and destroyed serially. The input is the original immutable interleaved dual CI16 window. Each lane gathers its own CI16 into preallocated memory. The scout reads that lane directly from the original interleaved window. The caller joins both typed rows in physical receiver order. The wrapper requires complete dual input. The single-receiver union port exposes existing per-antenna arithmetic for a single short window and leaves the old dual symbols and ABI layouts intact. [Protocol](PROTOCOL.md) · [Build and source locks](native-build.json)

The two recordings contributed 128 chronological native windows from segments 7 and 11. They are distinct from the earlier hotpath study's segments 0 and 4. All scheduled windows had valid complete IQ. Mode, role and capture IDs remain separate in all 2,304 measured calls. Every ordered scientific field, hint and union support record was identical across the three roles on 256 stock/fifth window comparisons. The 24 control comparisons cover zero IQ, both signed pilot edges, physically silent RX0 and RX1 and both absent hints. The zero and silent lanes had no gated candidate. The planted physical lanes remained gated. Absent hints gave the same public detector rows as stock. [Native evidence](native-measurements.json.gz) · [Seal](native-lock.json)

## Same-core response and compute

For each recording the serial control and the sequential split use the same caller core as parallel. Parallel adds the second fixed physical core. The primary lane is CPU18 on DS26 and CPU19 on DS29, with the opposite helper. All three roles use the same built release and warmed detector data, with measured order rotated. Input-to-typed and input-to-decoded clocks both start with a complete dual CI16 buffer. The typed boundary includes the join. The decoded boundary includes conversion of both returned rows. Raw archive reads, file serialization and position fitting have separate clocks.

| Detector and role | Decoded wall p50 / p95 | Total process CPU p50 | Both rows within 20 ms |
|---|---:|---:|---:|
| Stock serial dual | 25.84 / 46.71 ms | 24.45 ms | 12 / 384 |
| Stock split serial | 26.69 / 38.39 ms | 25.58 ms | 6 / 384 |
| Stock parallel | 16.04 / 33.62 ms | 26.93 ms | 293 / 384 |
| Fifth serial dual | 32.05 / 51.60 ms | 30.85 ms | 0 / 384 |
| Fifth split serial | 33.43 / 51.55 ms | 32.25 ms | 0 / 384 |
| Fifth parallel | 19.64 / 45.15 ms | 33.40 ms | 203 / 384 |

The two fifth-center lanes used 16.70 and 16.38 ms median thread CPU, including their gather and native work. Parallel total median CPU was 8.3% above serial dual and 3.6% above the same split run sequentially. In the parallel fifth mode the typed-only row boundary met 20 ms on 210/384 calls. Higher-tail wall values include elapsed host scheduling effects as well as detector service. [Timing distributions by recording and mode](native-summary.csv)

Separate fresh processes warmed one role each on eight actual visits and reported peak RSS across both detector modes. Serial dual used 198.2–198.3 MiB, split serial 222.9 MiB and split parallel 224.7–225.2 MiB across the two recordings. These include the common Python harness. [Isolated process memory](native-memory-isolated.jsonl)

## Complete arrival-paced replay

The full 299.986 s DS29-0316 IQ chronology ran at its recorded delivery times with the existing eight-packet decoder prefetch and one waiting detector slot. CPU18 handled the caller and CPU19 handled the persistent second lane. All 6,774 scheduled visits had valid dual IQ. The trial preserved each visit ID, sample counter, scheduled delivery, decoder-ready time and terminal disposition. All 6,423 emitted native payloads matched their authenticated all-valid fifth-center counterparts byte for byte. [Paced figure](paced/paced-dual-lane.png) · [Per-visit trace](paced/paced-events.json.gz) · [Paced seal](paced/paced-lock.json)

| Recorded-delivery result | Historical serial fifth | Parallel fifth |
|---|---:|---:|
| All physical visits | 6,774 | 6,774 |
| Emitted / dropped | 6,719 / 55 | 6,423 / 351 |
| Decoder ready after scheduled delivery | 0 | 26 |
| Emitted by next delivery, among packets with a next delivery | 3,566 / 6,718 | 5,605 / 6,422 |
| Native service wall p50 / p95 | 38.23 / 56.21 ms | 24.31 / 53.61 ms |
| Packet age p50 / p95 / p99 | 43.75 / 74.53 / 95.50 ms | 26.61 / 68.11 / 174.25 ms |
| Maximum packet age | 155.80 ms | 2,791.51 ms |
| Total measured detector CPU | 225.19 s | 224.78 s |

The historical control ran on the same saved schedule with a single detector core and its own host conditions. The parallel run finished in 301.13 s and used 245.3 MiB peak process RSS. Charged cgroup memory including file cache reached the 512 MiB cap, with zero swap and no OOM. A 2,790.41 ms detector service interval occurred in this replay. The largest detector CPU count for any packet was 53.63 ms. These clocks establish an elapsed timing tail without resolving its cause. Earlier completion was more frequent among emitted packets, while the two-core replay dropped substantially more input. The controlled native block above supplies the fixed-core timing comparison. [Paced summary](paced/paced-summary.json) · [Cgroup witness](paced/witness.json) · [Historical and new comparison](paced/paced-comparison.csv)

## Position using the retained native packets

The actual phase-release fit on the retained parallel fifth packets returned a fix in each calibration arm in 96.75 s. Both arms use identical observations, candidate sets, causal TLE and offered tile. Geographic errors use the held roof coordinate. RF RMS is conditional on each fit. The historical paced and complete fifth rows use their own authenticated observation sets. The standard charts also show the original v5 options, which use capture-era detections. [Zero calibration](paced/position-charts/c0/dual-lane-paced-position.png) · [Fitted calibration](paced/position-charts/fitted_c/dual-lane-paced-position.png) · [Position and RF values](paced/position-scores.csv) · [Score seal](paced/position-score-lock.json)

| Fifth-center input | Error, zero / fitted | Conditional RF RMS, zero / fitted |
|---|---:|---:|
| Parallel paced, 351 dropped | 0.426 / 0.424 km | 124.104 / 124.099 Hz |
| Historical serial paced, 55 dropped | 0.725 / 0.682 km | 122.289 / 122.302 Hz |
| All valid archived packets | 0.218 / 0.218 km | 120.068 / 120.063 Hz |

This is a host replay of recorded IQ and a separate retrospective roof fit. The 20 ms target concerns dual native detector output. Geographic fit time is separate. The single physical recording cannot establish the usual loss rate or performance on a live device.

## Reproduction

The Linux x86-64 archive contains both measured libraries, their build recipe, the generated scout and the adapted detector source. The tracked builder derives them from the published native-hotpath source closure with the pinned FFTW/compiler inputs. The first paced controller preflight stopped before replay because its stripped environment lacked a dependency imported only for reporting. Deferring those imports allowed the measured replay to complete with the already-qualified libraries. Ruff formatting left the measured evaluator and paced controller ASTs unchanged. The reproduction seal verifies both original source hashes against archived snapshots. [Measured library archive](dual-lane-linux-x86_64.tar.gz) · [Controller preflight](paced/preflight/service.log) · [Reproduction lock](reproduction-lock.json)
