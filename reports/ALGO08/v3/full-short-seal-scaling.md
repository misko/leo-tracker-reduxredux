# Charge detection sealing once per recording

The cold-prefix transfers had scaled the entire reader-to-sealed-file time with compressed size. Only the reader rate should scale that way in this model. The immutable detection write, fsync, readback and verification occur once per recording. Separating them changes the best combined prefetch and arena projection from **0.562 / 0.581** to **0.472 / 0.491** of historical time in the favorable solver scenario with an optimistic seal and startup excluded. A stressed seal gives **0.483 / 0.503**. With measured worker overhead added, both variants miss the aggregate half-time gate.

## Saved durability calibration

The two reversed repetitions wrote the saved 140,853-byte stock prefix and the saved 5,590,695-byte full DS30-0008 detector file to fresh private XFS paths using the original `immutable_json`. Both byte digests, original source fields and the rederived analysis binding passed. The raw authority was carried from the pinned saved document. No I/Q or recording index was read, so this test did not recompute raw authority from the waveform hashes or traverse a recording.

| Pair order | File | Canonicalization CPU ms | Readback / parse / verification CPU ms | File / directory fsync elapsed ms | Total CPU ms | Total elapsed ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1, first | Prefix | 0.706 | 0.037 / 5.171 / 0.718 | 255.389 / 2.789 | 7.178 | 265.116 |
| 1, second | Full | 27.320 | 1.536 / 23.366 / 26.149 | 70.065 / 32.659 | 80.285 | 182.499 |
| 2, first | Full | 26.845 | 1.551 / 22.395 / 26.194 | 195.079 / 17.676 | 79.476 | 291.015 |
| 2, second | Prefix | 0.728 | 0.031 / 0.497 / 0.679 | 22.966 / 3.495 | 2.420 | 28.666 |

Canonicalization, parsing and binding verification CPU increased with the larger JSON. The much larger spread in elapsed came from synchronization and other non-CPU wait. In the first pair the small file took longer than the full file. File fsync includes flushing data and can depend on file size and other load. Filesystem wait is not a constant and can correlate with the disk conditions that affect reader throughput. The common scenarios charge **0.1825 s** once from the faster measured full seal or **1.4071 s** once from the higher measured full seal CPU of 80.3 ms plus the largest previously observed seal wall-minus-CPU residual of 1.327 s. These are sensitivity points for a measured full-file size, with no assumption that they bound other recordings.

## Reader rate and seal at the two boundaries

| Study | Pair | Arm | Reader MB/s | Through-seal MB/s | Seal elapsed / CPU ms | Omitted worker elapsed s |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Receiver | 1 | Installed | 148.32 | 135.39 | 149.449 / 2.930 | 1.912 |
| Receiver | 1 | Full-short | 167.93 | 164.05 | 32.660 / 2.739 | 1.842 |
| Receiver | 2 | Full-short | 231.52 | 230.15 | 5.978 / 2.619 | 1.881 |
| Receiver | 2 | Installed | 141.91 | 141.15 | 8.859 / 2.432 | 1.887 |
| Ingress | 1 | Released hints | 216.49 | 96.63 | 1,329.704 / 2.938 | 1.868 |
| Ingress | 1 | Prefetch + arena | 196.73 | 137.89 | 503.376 / 2.905 | 1.814 |
| Ingress | 2 | Prefetch + arena | 228.27 | 177.40 | 291.556 / 3.053 | 1.895 |
| Ingress | 2 | Released hints | 218.57 | 102.81 | 1,195.514 / 3.139 | 1.905 |

The apparent throughput advantage of the combined ingress in both sealed-prefix pairs becomes one slower and one faster reader result. The earlier receiver comparison had much smaller seal wait. Its fastest run changes little before the once-per-file charge is added. The worker sensitivity charges measured interpreter, imports and process work outside the observed reader and seal once per recording. That overhead remains separate from the common durable output.

## Corrected 55-file projections

The 23.482 s scenario below used the finalist-race experiment. A later run timed the full live route, including its unconditional regional check, at 33.677 CPU s on the same dense detector input. With that measurement, the fastest signed-reader scenario projects 0.539 median and 0.553 summed elapsed with optimistic sealing and worker overhead. [Complete-route budget and both reader rates](full-short-transfer.md)

Each instrumented attempt now uses recorded compressed MB divided by the observed reader rate, one common detector seal, the historical solve time times the supplied fraction, and the original terminal-to-exit time. The three failures without stage instrumentation keep their original elapsed. Historical denominators are unchanged. The table gives median individual and summed elapsed relative to their measured historical totals. Each gate requires at most 0.5.

| Solve scaling | Path and reader MB/s | Former through-seal transfer | Optimistic once | Stressed once | Optimistic once + worker | Stressed once + worker |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 23.482/60.966 | Full-short 167.93 | .595 / .614 | .586 / .606 | .597 / .617 | .603 / .623 | .613 / .634 |
| 23.482/60.966 | Full-short 231.52 | .468 / .487 | .468 / .487 | .479 / .498 | .484 / .504 | .495 / .515 |
| 23.482/60.966 | Released hints 216.49 | .921 / .924 | .490 / .509 | .500 / .520 | .506 / .526 | .517 / .537 |
| 23.482/60.966 | Released hints 218.57 | .871 / .879 | .486 / .505 | .497 / .517 | .503 / .523 | .514 / .534 |
| 23.482/60.966 | Prefetch + arena 196.73 | .679 / .699 | .523 / .542 | .534 / .554 | .539 / .559 | .550 / .570 |
| 23.482/60.966 | Prefetch + arena 228.27 | .562 / .581 | .472 / .491 | .483 / .503 | .489 / .509 | .500 / .520 |
| 11.680/21.383 | Full-short 231.52 | .520 / .534 | .520 / .534 | .531 / .545 | .537 / .551 | .548 / .562 |
| 11.680/21.383 | Released hints 218.57 | .911 / .925 | .539 / .552 | .549 / .564 | .555 / .570 | .566 / .581 |
| 11.680/21.383 | Prefetch + arena 228.27 | .614 / .628 | .525 / .538 | .535 / .550 | .541 / .556 | .552 / .567 |

The quickest earlier full-short reader meets the favorable gates under both seal scenarios without the measured worker charge. The fastest combined reader meets them only in the optimistic no-worker model. Its aggregate gate needs 222.21 MB/s with the optimistic seal and 230.15 MB/s with the stressed seal, or 234.74 and 243.62 MB/s with measured worker overhead. The second solver scenario misses under all sampled rates. The receipt gives all eight rates and both solver scenarios, including warm and cold subsets and required reader rates.

For DS30-0016, use the complete physical measurement. Launch through exit was 14.521 s stock and 9.472 s candidate, with the stock starting cold and the candidate starting warm. The complete pair establishes its own two-arm geographic result and did not reach 2× elapsed speed. [Physical pilot and scientific receipt](full-short-physical.md)

[Frozen calibration rules](full-short-seal-scaling-protocol.md) · [Measured calibration and recomputed projections](measurements/full-short-seal-scaling.json) · [Receiver prefix experiment](full-short-cold.md) · [Prefetch and arena experiment](full-short-arena.md)
