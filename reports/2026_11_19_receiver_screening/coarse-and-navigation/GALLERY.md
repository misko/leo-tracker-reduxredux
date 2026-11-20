# Coarse and navigation gallery

[Browse the benchmark](benchmark/index.html) · [Download the offline ZIP](benchmark/modification-charts.zip) · [Verify exported files](benchmark/pack-lock.json)

The pack contains **17 position comparisons** with both calibration views and **12 stage charts**. It includes 46 standalone PNGs, the PDF books, the plotted values, and their hashes.

| Study | Position comparisons | Stage charts | Measurement boundary |
| --- | ---: | ---: | --- |
| [Adaptive visits](adaptive-visits/README.md) | 1 | 1 | Archived packet substitutions and fresh compact fits on six held recordings, with modeled detector work |
| [Selected calibration](arm-execution/README.md) | 2 | 1 | Authenticated factors through paired publication on four recordings with an original or shifted offer |
| [Array closure](array-closure/README.md) | 8 | 1 | Exact simultaneous phase and bracketed wire-stable phase, with anonymous and author-ID comparisons at measured sites |
| [Clock transfer](clock-transfer/README.md) | 4 | 1 | Held carrier forecasts and position diagnostics on four measured roof recordings and a separate simulated site |
| [Coarse waveform](coarse-waveform/README.md) | 1 | 1 | Complete DS26-0162 nested-primary replay through compact position and matched archive controls |
| [Coarse FFT length](fft-length/README.md) | 0 | 1 | Development-only plan selection and complete detector comparisons on eight held stereo visits |
| [Nested anchors](nested-anchors/README.md) | 0 | 1 | Shared and recomputed retry grids within the revised primary schedule, plus a separate comparison with the original schedule |
| [Portable candidate verifier](portable-verifier/README.md) | 0 | 1 | Native host timings and emulated ARM agreement within tolerance from supplied coarse epochs through fractional GLRT |
| [Scan accounting](scan-accounting/README.md) | 1 | 1 | Collector timing for the same authenticated shards and fresh compact fits on three shared assembled inputs |
| [Seeded acquisition](seeded-acquisition/README.md) | 0 | 1 | Upper-edge held pilot searches with shifted-seed and approximately CPU-matched native controls |
| [Sliding pilot bank](sliding-pilot-bank/README.md) | 0 | 1 | Development folded-map comparisons and complete detector timing on six held stereo visits |
| [Winner bound](winner-bound/README.md) | 0 | 1 | Saved stereo visits and matched spectral repeats through fractional spectrum timing |

The roof plots show all four original v5 options on the matched recordings. Transfer estimates use their sealed offers and documented controls. The tables retain each scheduled attempt and mark forced estimates separately. The array estimators and clock-transfer model leave fitted calibration unavailable. Clock transfer reports its `c = 0` gauge choice. [Calibration views](benchmark/charts/index.html) · [Position and frequency summaries](benchmark/summary.csv) · [Per-recording scores](benchmark/position-rf.csv) · [Plotted position values](benchmark/positions.csv)

The selected-calibration timing services still run both numerical arms before returning the requested result. Scan-accounting collector times cover reading, decoding, verification, and hashing. The linked source report gives the detector and compact service clocks separately. [Stage figures and measurements](benchmark/stage-charts/README.md) · [Descriptor and receipt inventory](benchmark/study-evidence.json)

## Rebuild the benchmark

```sh
study=reports/2026_11_19_receiver_screening/coarse-and-navigation
work=$(mktemp -d)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study "$study" --pack --out "$work/benchmark"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  "$work/benchmark/charts" --expected-charts 17
```
