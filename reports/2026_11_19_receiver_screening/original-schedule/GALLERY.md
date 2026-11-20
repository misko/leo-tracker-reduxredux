# Original schedule gallery

[Browse the benchmark](benchmark/index.html) · [Download the offline ZIP](benchmark/modification-charts.zip) · [Verify exported files](benchmark/pack-lock.json)

The pack contains **15 position comparisons** with both calibration views and **13 stage charts**. It includes 43 standalone PNGs, the PDF books, 1,051 plotted position rows, stage measurements, and their hashes.

| Study | Position comparisons | Stage charts | Measurement boundary |
| --- | ---: | ---: | --- |
| [Accelerated command](accelerated-command/README.md) | 1 | 1 | Primary raw timeout and the separate same-case completion check, with matched archived-factor compact fits |
| [Beacon transfer](beacon-transfer/README.md) | 3 | 1 | Leave-site-out carrier levels across eight measured StarLoc sites and three offer conditions |
| [Coarse CFO](coarse-cfo/README.md) | 0 | 1 | Interleaved coarse CFO trials and held full-detector timing against the measured-plan 256 bank |
| [Code and carrier](code-carrier/README.md) | 4 | 1 | Matched held intervals on four roof recordings and a separate simulated site |
| [Fast calibration](fast-calibration/README.md) | 1 | 1 | Frozen CFO correction on held gated factors and matched compact fits |
| [FFT waveform](fft-waveform/README.md) | 1 | 1 | Complete DS29-0519 replay with the stored 256-point plan and matched earlier complete controls |
| [Fine epoch reuse](fine-epoch-reuse/README.md) | 0 | 1 | Complete detector on an outcome-blind timing panel and a separate set of recheck witnesses |
| [Geometry schedule](geometry-schedule/README.md) | 1 | 1 | Causal forecasts, matched archived packet substitutions, modeled detector work and separately measured compact fits |
| [Portable coarse detector](portable-coarse/README.md) | 0 | 1 | Saved I/Q through acquisition, peer retry and fractional GLRT, with host timing and separate ARM emulation |
| [Prague transfer](prague-transfer/README.md) | 2 | 1 | Author-assisted Doppler and tied ECEF from two sessions at one CTU roof |
| [Spectral rewrite](spectral-rewrite/README.md) | 0 | 1 | Resident I/Q through complete detector output and separate exact/control spectral profiling |
| [Track preparation](track-preparation/README.md) | 2 | 1 | Authenticated native factors through both compact arms, with original and shifted offers shown separately |
| [Verifier integration](verifier-integration/README.md) | 0 | 1 | Resident saved I/Q through the original coarse dispatcher, C verification and peer retry |

The roof plots include all four original v5 options on the matched recordings. Withheld, timed-out, and unavailable attempts remain in the scheduled denominators. The transfer plots label fixed offer centres and forced diagnostics. Beacon transfer, code and carrier, and the author-assisted Prague estimators mark fitted calibration as unavailable. The Prague panels identify the survey-assisted track extraction and uncertainty in orbit availability. [Calibration views](benchmark/charts/index.html) · [Position and frequency summaries](benchmark/summary.csv) · [Per-recording scores](benchmark/position-rf.csv) · [Plotted position values](benchmark/positions.csv)

The accelerated stage separates per-visit detector clocks from elapsed service times. The raw CPU schedules have separate labels. Position plots retain the primary timeout, the recorded completion result, the archive fit, and the historical v5 timeout. [Stage figures and measurements](benchmark/stage-charts/README.md) · [Descriptor and receipt inventory](benchmark/study-evidence.json)

## Rebuild the benchmark

```sh
study=reports/2026_11_19_receiver_screening/original-schedule
work=$(mktemp -d)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study "$study" --pack --out "$work/benchmark"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  "$work/benchmark/charts" --expected-charts 15
```
