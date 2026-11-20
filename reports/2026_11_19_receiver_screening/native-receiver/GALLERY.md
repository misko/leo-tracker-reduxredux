# Native receiver benchmark gallery

[Browse every comparison](benchmark/index.html) · [Download the offline ZIP](benchmark/modification-charts.zip) · [Verify the exported files](benchmark/pack-lock.json)

The gallery contains 19 position comparisons with both calibration views and 12 stage charts. The pack includes 50 standalone PNGs, the PDF books, and the values behind each chart.

| Study | Inputs and comparison |
| --- | --- |
| [Portable field receiver](portable-field/README.md) | Full signed DS26-0020 I/Q through the compact position solver, with an archived-factor fit and the original v5 roles |
| [Portable saved-recording command](portable-command/README.md) | Full signed upper-edge DS29-0082 I/Q through position, with a separate earlier exact replay |
| [Verifier memory](verifier-memory/README.md) | Held stereo I/Q through both complete detector builds, with matched output and working-set measurements |
| [Coarse tiles](coarse-tiles/README.md) | Symmetric-carrier coarse acquisition, original seed selection, and the full stereo verifier on three capture producers |
| [Detector footprint](detector-footprint/README.md) | Executed Python and C source on three fixed, decoded I/Q visits |
| [Pilot cancellation](pilot-cancellation/README.md) | Saved stereo I/Q through pilot cancellation, recovery of secondary candidates, and held waveform checks |
| [Catalogue checksum](catalog-checksum/README.md) | Isolated checksum comparison through stored-GLRT localization and a separate parser timing study |
| [Track quadrature](track-quadrature/README.md) | Six stored-GLRT captures through all-sample, uniform eight-point, and Gauss–Lobatto orbit screening and exact final fits |
| [Session geometry](session-geometry/README.md) | Held visits at one Prague rooftop and one simulated site, with transferred positions and separately scored frequency residuals |
| [Site region sets](site-region-sets/README.md) | Competing area offers at eight measured StarLoc sites and a simulated reference scene |
| [Bounded arrival](native-arrival/README.md) | Queues modeled from native detector service measurements, one short paced detector run, and compact fits on retained probes |

Roof pages compare both calibration arms against the four original v5 options on the same recordings and original offers. Timeouts, failures, and withheld fixes remain in the scheduled counts. Forced estimates have their own rows. Transfer pages identify the receiver inputs and offer conditions, including when fitted calibration is unavailable. [Calibration switch](benchmark/charts/index.html) · [Plotted position rows](benchmark/positions.csv)

Position is unmeasured in the standalone verifier, coarse tiles, detector footprint, pilot cancellation, and catalogue parser stages. Geographic errors and RF scores have separate columns. [Stage charts and plotted data](benchmark/stage-charts/README.md) · [Position and RF summaries](benchmark/summary.csv) · [Per-recording scores](benchmark/position-rf.csv) · [Descriptors and receipts](benchmark/study-evidence.json)

## Rebuild the gallery

Run from the repository root. The rebuild reads the sealed predictions and stage measurements.

```sh
study=reports/2026_11_19_receiver_screening/native-receiver
work=$(mktemp -d)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study "$study" --pack --out "$work/benchmark"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  "$work/benchmark/charts" --expected-charts 19
```
