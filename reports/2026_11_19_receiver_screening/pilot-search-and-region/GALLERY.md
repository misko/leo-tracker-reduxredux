# Pilot search and region gallery

[Browse the benchmark](benchmark/index.html) · [Download the offline ZIP](benchmark/modification-charts.zip) · [Verify exported files](benchmark/pack-lock.json)

The pack contains **12 position comparisons** with both calibration settings and **8 stage charts**. Each of the 32 plots has a standalone PNG. The ZIP also contains the PDF books, 2,098 plotted position rows, stage measurements, and hashes.

| Study | Position comparisons | Stage charts | Measured boundary |
| --- | ---: | ---: | --- |
| [Coarse basis](coarse-basis/README.md) | 0 | 1 | Full coarse grid and detector gate parity on held stereo visits |
| [Staggered RF Doppler](differenced-orbits/README.md) | 4 | 1 | Carrier support and sealed original, displaced, and orbit-time-sham offers |
| [Field-exact waveform](field-exact-waveform/README.md) | 1 | 1 | Complete DS29-0082 waveform through candidate projection and compact position |
| [Final region guard](final-region/README.md) | 3 | 0 | Original roof offers, released controls, and prospective recorded offers |
| [Pruned fine CFO search](fine-search/README.md) | 0 | 1 | Paired complete detector CPU and output agreement on saved stereo visits |
| [RF routing panel](rf-lane-panel/README.md) | 1 | 1 | Archived stereo routing, original-detector work, and position on ten recordings |
| [RF routing positions](rf-lane-position/README.md) | 2 | 0 | Recorded-time and 20 ms packet cutoffs through position |
| [RF routing waveform](rf-lane-waveform/README.md) | 0 | 1 | Exclusive RF assignment through detector completion on two complete recordings |
| [Single-pass anchors](single-pass/README.md) | 1 | 2 | Outcome-blind detector panel and [position replay](single-pass/position/README.md) using saved IQ for retry-eligible visits and archived packets for the rest |

Each position plot uses its own scheduled recordings or offers. The tables count published, withheld, failed, timed-out, unavailable, and unmeasured outcomes. Numerical estimates saved alongside a withholding appear as forced diagnostics. The fitted calibration arm is unavailable for the staggered rate contrasts because differentiation removes the constant RF term. The original v5 reference retains its two measured arms. [Calibration views](benchmark/charts/index.html) · [Position and frequency summaries](benchmark/summary.csv) · [Per-recording scores](benchmark/position-rf.csv) · [Plotted position values](benchmark/positions.csv)

Stage figures use the sample and measurement boundary stated on each chart. Their data include detector work, support, timing, and candidate agreement. [Stage figures and measurements](benchmark/stage-charts/README.md) · [Descriptor and receipt inventory](benchmark/study-evidence.json)

## Rebuild the benchmark

```sh
study=reports/2026_11_19_receiver_screening/pilot-search-and-region
work=$(mktemp -d)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study "$study" --pack --out "$work/benchmark"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  "$work/benchmark/charts" --expected-charts 12
```
