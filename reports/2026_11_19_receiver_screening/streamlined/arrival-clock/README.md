# Detector queues on recorded delivery clocks

On the two ordinary recordings, one worker and one waiting slot handled every valid detector call in the reconstructed queue. Two workers handled both recordings with zero waiting slots. The same buffer sizes sufficed when measured native wall durations replaced CPU durations. A real 96-visit pacing trial reproduced the detector output and observed larger scheduling delays than the CPU model. [Queue figure](queue.png) · [Complete finite-buffer results](queue.csv) · [Pacing measurements](paced-summary.json)

## What the clocks measure

The acquisition worker stamps `host_delivery_clock` immediately after the provider iterator returns the IQ block. It then views the samples and performs quality checks. Both installed acquisition sources had the same SHA-256 as the linked source. The clocks describe arrivals at the acquisition host, after provider delivery, with validation and detector work still ahead. They have a different origin from the RF sample counter and the recorded capture span. Subtracting the first monotonic stamp gives 299.966 and 299.997 seconds of delivery time. Median adjacent delivery gaps were 43.62 and 43.45 ms; the shortest were 17.30 and 14.39 ms. [Clock implementation](../../../../src/leo/acquisition/continuous_window_ppu.py) · [Sealed delivery events](delivery-events.json.gz) · [Source lock](source-lock.json)

The ordinary factor SHA binds every delivery clock and capture exclusion. The IQ replay has two serial lanes on alternating segment indexes. The scorer checks the lane partition, segment manifest SHA, visit sequence, raw clock and exclusion against the native archive. It joins each lane's duration vector to its native calls in lane order and then restores physical visit order. The scheduled replay has a separate authenticated vector of actual native calls and explicitly skipped valid visits under the same physical arrival sequence. [Ordinary whole-IQ method](../whole-pair/README.md) · [Recorded-schedule method](../iq-schedule/README.md)

## Finite FCFS model

Each valid retained visit is one two-receiver detector job. At its delivery, the earliest available worker starts the job or the shared waiting queue takes it if a slot is free. An arrival drops only when all workers and all waiting slots are occupied. Completion or dispatch at the exact delivery time frees capacity first. Equal delivery times use physical visit order. Invalid and intentionally skipped visits remain on the arrival clock, use zero modeled native service and count separately from buffer loss. The trace supplies the duration of a job once it is admitted. Admission never consults a future arrival, skip decision or service duration.

The CPU model carries only the observed native detector service demand. The wall model reuses per-call native wall intervals from the capped archive lanes and preserves measured long calls. Both assume the same service times on one or two comparable host cores. Read, authentication, decode, quality checks, handoff overhead within each call, and scheduler conditions of a new long-running pipeline lie outside these two reconstructions. [All capacities and latency percentiles](queue.csv)

| Ordinary recording | Physical / invalid / detector | Native CPU total | One worker, zero-wait losses CPU / wall | One-worker lossless P50 / P95 / P99 latency, CPU model | One-worker lossless drain | Earliest modeled complete position after last delivery |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 6,769 / 4 / 6,765 | 184.43 s | 9 / 10 | 27.13 / 33.09 / 35.74 ms | 27.67 ms | 69.126 s |
| DS29-0082 | 6,772 / 1,904 / 4,868 | 129.13 s | 1 / 6 | 26.32 / 31.88 / 34.88 ms | 23.82 ms | 42.178 s |

At that one-slot operating point, 6,755/6,764 and 4,864/4,867 completed jobs with a following physical delivery finished by it. Most native calls still exceeded 20 ms. The whole-pair wall measurements show 86/6,765 and 44/4,868 at or below 20 ms. Thus processing all visits depends on delivery intervals and buffering as well as native call duration. [Per-call reference](../whole-pair/README.md#individual-detector-calls)

| Recorded schedule | Invalid / policy skipped / detector | Native CPU total | Lossless slots, 1 worker CPU / wall | Lossless slots, 2 workers CPU / wall | Earliest modeled complete position after last delivery, CPU model |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 4 / 1,690 / 5,075 | 144.54 s | 1 / 9 | 0 / 1 | 52.218 s |
| DS29-0082 | 1,904 / 1,212 / 3,656 | 104.22 s | 1 / 2 | 0 / 0 | 42.601 s |

The time to a complete position adds the predicted drain after the last delivery to the measured factor assembly, handoff and corresponding compact cavity solve. Every reported position-time row has zero buffer losses and a matching completed control. The two complete prediction books provide the observed positions on their stated detector inputs. This queue study produces timing estimates only. [Whole-IQ position plots](../whole-pair/plots/index.html) · [Scheduled position plots](../iq-schedule/plots/index.html)

## Short real-time wall replay

CPU 16 at nice 10 replayed the first 96 physical visits of ordinary DS26-0036 with the same recorded detector binary and source adapter. The raw decoder authenticated and prefetched the prefix before timing. A producer released the resident IQ on the recorded monotonic offsets across 4.205 s. A pinned worker thread took the visits in FCFS order, ran the native detector and compared both receiver rows to the ordinary factors. All 96 matched. The finite queue held up to four waiting visits and did not fill its 32 slots. After the last actual release it drained in 21.17 ms.

| Prefix latency, ms | P50 | P95 | P99 | Maximum |
|---|---:|---:|---:|---:|
| Native CPU reconstruction from the archived prefix | 26.05 | 31.30 | 31.74 | 32.47 |
| Measured release to completed detector and adapter | 24.70 | 67.14 | 113.70 | 200.68 |
| Measured scheduled release lateness | 0.079 | 1.942 | 93.124 | 132.107 |

The short one-core result measures scheduling and the detector adapter on resident IQ. It preserves the original capture and detector arrays and excludes live radio delivery, steady-state archive I/O and a position solve. The measured latency tails leave the full-recording model's buffer minimum conditional on its service trace. [Exact paced observations](paced.json) · [Per-visit wall timings](paced-visits.csv)

## Reproduce

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.arrival_clock score --out /tmp/arrival-clock
.venv/bin/pytest -q tests/pipeline_eval/test_arrival_clock.py
```

Scoring uses the packaged monotonic event projection, sealed source lock and pacing record. On the source host, `arrival_clock extract --include-schedule` verifies and projects the two earlier whole-IQ runs and the two scheduled runs. Access to their local raw replay directories is required for extraction. The original recorder, archived IQ, native detector, full replay receipts and position chart books stay intact.
