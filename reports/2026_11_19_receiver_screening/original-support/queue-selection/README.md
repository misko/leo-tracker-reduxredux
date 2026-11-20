# Which original detector windows can one waiting slot retain?

One modeled worker retained about one recording window in ten. Giving priority to the least recently processed RF balanced the eight channels at 59–65 visits apiece. FIFO gave them 29–93. All three one-worker sets left the compact position solver without a curved Doppler track it could use. This result uses genuine dual-antenna measurements and actual position fits. The admissions came from a chronological queue model. [Individual position decisions](scores.csv) · [One-worker distribution](charts/fitted_c/original-queue-1.png)

The model starts from all 6,772 original DS29-0082 host delivery times. It charges each of the 4,868 valid visits its own measured original-detector CPU time from the preceding complete capture replay. A single waiting slot can keep the first arrival, keep the latest arrival, or replace the waiter when the incoming RF was served less recently. The last rule needs only the RF and the time each lane last started. Each rule keeps the original 1,904 hardware exclusions. The modeled receiver never processes two windows on the same core at the same time. [Protocol](PROTOCOL.md) · [Frozen selections including start and completion clocks](forecasts.json.gz) · [Source and policy checksum](forecast-lock.json)

| Model and waiting rule | Valid visits retained | Smallest–largest RF count | Position error at zero / fitted calibration | Conditional RF RMS at zero / fitted calibration |
| --- | ---: | ---: | ---: | ---: |
| One worker, first arrival | 507 | 29–93 | Withheld | — |
| One worker, latest arrival | 489 | 40–110 | Withheld | — |
| One worker, least recently started RF | 497 | 59–65 | Withheld | — |
| Four workers, first arrival | 2,004 | 139–360 | 1.917 / 1.840 km | 62.15 / 62.29 Hz |
| Four workers, latest arrival | 1,951 | 126–386 | 4.375 / 4.209 km | 61.13 / 61.15 Hz |
| Four workers, least recently started RF | 1,975 | 180–316 | 3.749 / 3.778 km | 87.48 / 87.44 Hz |
| Complete original detector, measured control | 4,868 | All valid opportunities | 0.568 / 0.516 km | 97.00 / 96.68 Hz |

With four modeled workers the three new compact fits used 805, 804 and 819 gated observations. The control used 1,868. The four-worker first-arrival rule had the lowest error of the three in both arms. Every four-worker fitted error exceeded the +10% allowance relative to original no-repair v5, whose fitted error was 0.517 km. Lower RF residuals on the reduced observation sets coincided with larger geographic errors. The six new position services used at most 436 MiB under individually enforced 512 MiB limits with zero swap. [Four-worker position distribution and all v5 options](charts/fitted_c/original-queue-4.png) · [Zero-calibration distribution](charts/c0/original-queue-4.png) · [Position jobs and resource receipts](positions.jsonl.gz)

The capacity chart includes one, two, four, eight and twelve modeled workers. Even twelve workers with one shared waiting slot retained at most 4,574 of 4,868 valid visits. Every original detector call on this waveform exceeded 20 ms of CPU. Draining the final queued work took about one second beyond the last arrival in most configurations. This clock excludes source decoding and operating-system contention. The measured arrival runs have separate raw traces and positions. [Capacity chart](capacity.png) · [Exact timing table](timing.csv) · [Measured complete original-GLRT timing](../../antenna-confirmation/capture-whole/README.md)

Two independent single-worker replays now measure actual admissions on the same 6,772 arrival timestamps. FIFO emitted 387 valid visits, of which 52 appeared among the 507 modeled selections. The least recently started RF rule emitted 370, of which 44 appeared among the 497 modeled selections. The actual and modeled visit sets thus had intersection-over-union of 6.18% and 5.35%. Every emitted receiver packet matched the full original reference at its actual visit. Both measured policies withheld in both calibration settings. A separately paced four-region detector on the same recording processed 4,836 valid visits and gave 2.485 / 2.340 km error. [Actual original FIFO and four-region receiver](../paced-original/README.md) · [Actual RF-aware waiting](../paced-rf/README.md)

To regenerate the comparison from the published evidence, run the command below from the checkout.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study reports/2026_11_19_receiver_screening/original-support/queue-selection \
  --out /tmp/original-queue-comparison
```
