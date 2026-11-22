# What still costs time in the single-core pipeline

## Building provenance once per selected orbit

The causal catalogue code recorded a new provenance dictionary, including age and snapshot digest, every time a newer set of elements became the incumbent for a satellite. The research refactor retains the winning snapshot reference and builds that dictionary once per satellite after scanning the eligible rows. Reads, epoch and collection cutoffs, tie ordering, output order and the satellite objects stay the same. The selector never receives receiver coordinates.

| Saved archive | Age window | Snapshots | Selected satellites | Median selector CPU, deployed → deferred |
|---|---:|---:|---:|---:|
| DS30-0374 | 48 h | 32 | 11,085 | 141 → 62 ms |
| DS30-0374 | 72 h | 47 | 11,190 | 253 → 125 ms |
| Southern simulation | 48 h | 23 | 10,937 | 84 → 46 ms |
| Southern simulation | 72 h | 35 | 11,189 | 152 → 69 ms |

The two implementations returned exactly the same satellite objects, names, numbers and provenance on all 24 timed calls. Digest-checked archive reads and parsing were performed before timing. Savings apply per invocation of the indicated window. Actual end-to-end gains depend on which catalogue policies a scan invokes. The frozen raw-to-web pairs in this report use the released selector. [Measurements](measurements/catalogue-winners.json) · [Reproduction harness](catalogue_winners_trial.py) · [Causal selection](../../../src/leo/operations/causal_tle_catalogue.py)

The second recording in the fixed DS30 order has a more expensive position solve than the first. We used its saved two-scan detections to measure that difference without reading the recording again. Stock solver CPU was **80.77 s on DS30-0008**, versus **34.01 s on DS30-0374**. Causal parsing and coarse salvage statistics reduced DS30-0008 to **72.66 s (1.11×)**. Both positions, ownership summaries, optimizer paths and all numerical grid values matched. Causal preparation fell from 7.79 to 5.03 CPU seconds and salvage from 12.04 to 7.11. Initial assignment still took 22.83 elapsed seconds, conservative recovery 17.20, family selection 8.64, signed evidence 2.51, cavity work 6.40 and final grid/evidence 10.37. These clocks begin at saved detections. [Receipts for both solvers](measurements/solver-costs.json.gz) · [Trial runner](solver_trial.py)

## Cheap periodicity test before running the receiver

At 10 MS/s, three nominal pilot frames occupy exactly 40,000 samples. For each antenna independently, take every sixteenth sample from five consecutive blocks of that length, subtract each block mean and compute normalized complex correlations across all ten block pairs. The maximum squared magnitude is insensitive to a constant carrier phase offset between blocks. Noise, independent carriers, varying gains and cancellation of overlapping components can all reduce the observed correlation. The experiment compares the score to actual verified factors from the frozen two-scan receiver.

The threshold of 0.00212 was fixed from a 5% union-bound approximation for independent white complex noise. Runtime ratios below charge the screen to every antenna and subtract the measured native time of skipped calls. They estimate receiver compute only, excluding I/Q verification and all later stages.

| Saved panel | Antenna lanes | Lanes skipped | Verified factors lost / available | Estimated screened / full native CPU |
|---|---:|---:|---:|---:|
| Physical DS26 development | 160 | 105 | 76 / 141 | 0.44 |
| Separate physical DS26 archive | 128 | 82 | 58 / 113 | 0.46 |
| Northern and southern simulated prefixes | 160 | 16 | 0 / 37 | 0.98 |

Even granting the best threshold on the development sample that kept every verified factor, **zero** physical development lanes could be skipped. That threshold skipped just one lane on the separate physical archive. The screen fails as an evidence-preserving shortcut. Testing the two simulated prefixes alone would have missed the physical losses. [Scores for every measured lane](measurements/coherence-screen.json.gz) · [Screen implementation](../../../tools/pipeline_eval/variants/experimental/coherence_screen.py)

## Repeated optimizer coordinates and final PNG encoding

- Caching exact coordinates inside a fixed regional fit avoids recomputing a residual when bound clipping revisits the same point. On DS30-0374 there were **12 cache hits and 578 misses in 80 fits**. Solver plus grid took 28.70 CPU seconds against an earlier 28.39-second control. Both endpoint and owner summaries matched. The observed reuse does not justify integration. [Implementation](../../../tools/pipeline_eval/variants/algo08_fit_reuse.py) · [Receipts](measurements/solver-costs.json.gz)
- Re-encoding the eight existing DS30-0374 rasters at the original compression level reproduced every published PNG byte. The two repeats used 1.02 CPU seconds. Level 1 used 0.66 seconds, with exactly the same decoded pixels, metadata and dimensions. Combined size rose from 11.52 to 13.01 MB. That saves about **0.36 CPU seconds** against the **28.69-second** remaining CPU budget on the physical case. This test covers encoding alone. The measured candidate continues to generate the original bytes. [PNG measurements](measurements/DS30-0374-png.json) · [Encoder trial](png_trial.py)
