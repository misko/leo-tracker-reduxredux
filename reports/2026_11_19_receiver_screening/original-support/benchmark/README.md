# Original GLRT support benchmark

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver original-support --out /var/tmp/original-support
```

Open [the position gallery](charts/index.html) to choose a receiver comparison and calibration setting. Each view includes the position error distribution and individual recordings. The command verifies the source-study seals and regenerates the gallery from their endpoints. It also writes [fix coverage, error and matched v5 allowances](summary.csv), [individual geography and RF values](position-rf.csv), [scoped timing summaries](timing-summary.csv) and [source and output hashes](benchmark-lock.json). The 5% and 10% allowances compare each eligible roof recording to its original no-repair v5 error. Original alternative v5 roles retain their own outcomes. Field offers have their own denominators and keep forced diagnostics separate.

## Same-recording checks

### Modeled and paced queues on DS29-0082

Both one-worker, one-waiting-visit policies saw 6,772 physical slots, of which 4,868 had valid capture support. FIFO ran on CPU10 and oldest-RF on CPU12. Visit IDs were compared after checking every original delivery clock, validity decision and sample counter range. Age runs from the recorded delivery time to native packet emission and conditions on emitted visits.

| Policy | Modeled emissions | Measured emissions | Shared visits | Jaccard | Median age, modeled / measured | P95 age, modeled / measured |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FIFO | 507 | 387 | 52 | 0.0618 | 1.093 / 1.361 s | 1.912 / 2.216 s |
| Oldest RF | 497 | 370 | 44 | 0.0535 | 0.898 / 1.279 s | 1.777 / 2.174 s |

Neither measured original-detector queue emitted a valid visit within 20 ms. The two measured policies shared 26 emitted visits. All four compact fits withheld in both calibration arms with `no_active_curvature`. The full capture-era original v5 reference fixed at 0.567 km with `c = 0` and 0.517 km with fitted `c`. The fast-four paced control has its own measured timings and position chart. The queue forecast substantially overestimated admission and had low overlap with actual emitted visits on this recording. [Visit overlap and clocks](queue-overlap.csv) · [Position and conditional RF](queue-position.csv) · [Paced source study](../paced-original/README.md)

### Direct and stored periodic acquisition on DS26-0162

The independently executed schedule and the stored-factor projection selected the identical 1,675 valid visits out of 6,772 slots. The 13,426 physical probe rows, 15,898 candidate records, delivery clocks, sample anchor and 59 hardware-invalid visit records matched exactly. The complete files carry different lineage metadata. The periodic and full-support compact comparisons also agreed on both numerical arms and frequency scores.

| Input | Position error, `c = 0` / fitted | Conditional RF RMS, `c = 0` / fitted |
| --- | ---: | ---: |
| Direct quarter schedule | 1.286 / 1.180 km | 72.974 / 73.000 Hz |
| Stored projection of the same schedule | 1.286 / 1.180 km | 72.974 / 73.000 Hz |
| Complete original factors through compact | 0.402 / 0.417 km | 47.467 / 47.460 Hz |
| Original v5 baseline | 0.399 / 0.415 km | 108.276 / 77.762 Hz |

The quarter schedule took 192.445 s of raw replay wall time over six workers, 855.184 detector CPU seconds and a separate 36.348 s compact fit. The stored projection ran only a factor-to-position fit. The full-support compact retained position within 5% of original v5 in both calibration arms on this recording. RF summaries are conditional on each fit’s selected tracks and support. [Parity and hashes](overlap.json) · [Position and RF](periodic-position.csv) · [Direct waveform study](../scheduled-waveform/README.md)

The prepared detector also ran on complete saved IQ from DS26-0237. It produced 60,306 candidates matching the original archive and reproduced the archived-factor compact errors of 0.353 km with `c = 0` and 0.262 km with fitted `c`. Both positions fell within 5% of original v5. [Per-arm prepared detector scores](../prepared-waveform/scores.csv)

## Wider stored-factor comparison

On the ten-recording rotating-dwell roster, full support fixed 10/10 and met both the 5% and 10% v5 allowances in both calibration arms. Two rotating RF lanes fixed 10/10 and met both allowances on 1/10 in each arm. Four rotating lanes also fixed 10/10 and met both allowances on 3/10 with `c = 0` and 2/10 with fitted `c`. These were compact fits to selected stored factors on the original recorded clock. [Rotating-dwell results](../rotating-dwell/summary.csv)

The queue and periodic checks each reuse one recording. The wider scheduling cohorts, detector kernel tests, solver-reuse cohort and independent offer panels keep their own denominators and clock scopes. The independent antenna activity screen preserved 270/270 positive lanes across 384 held visits and changed detector CPU P50 from 20.48 to 20.41 ms. It contributes stage evidence only. This benchmark regenerates analysis and plots from saved evidence. [Antenna activity screen](../lane-screen/README.md) · [Source selection and measurement boundaries](PROTOCOL.md)
